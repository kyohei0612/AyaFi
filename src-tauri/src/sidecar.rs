//! Python sidecar lifecycle management.
//!
//! Spawns `python scripts/sidecar.py` (dev) or the bundled PyInstaller exe
//! (release, Stage 6+) and bridges requests/responses over stdin/stdout using
//! the NDJSON protocol defined in ADR-003.
//!
//! Stage 1 scope: spawn + send_request round-trip with timeout. Automatic
//! restart, heartbeat monitoring, and cancel propagation land in Stage 3 per
//! ADR-010.

use std::collections::HashMap;
use std::path::PathBuf;
use std::process::Stdio;
use std::sync::Arc;
use std::time::Duration;

use anyhow::{anyhow, Context, Result};
use serde::Serialize;
use serde_json::Value;
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio::process::{Child, ChildStdin, Command};
use tokio::sync::{oneshot, Mutex};
use tokio::time::timeout;
use uuid::Uuid;

const PROTOCOL_SCHEMA_VERSION: u32 = 1;
const REQUEST_TIMEOUT_GRACE_SEC: u64 = 5;

type PendingMap = HashMap<String, oneshot::Sender<Value>>;

#[derive(Serialize)]
struct OutgoingRequest<'a> {
    schema_version: u32,
    request_id: String,
    action: &'a str,
    params: Value,
    timeout_sec: f64,
}

/// Handle to a running Python sidecar process.
///
/// Cloning is cheap (all interior state is shared `Arc`). Dropping the last
/// clone kills the child process (`kill_on_drop`).
#[derive(Clone)]
pub struct Sidecar {
    stdin: Arc<Mutex<ChildStdin>>,
    pending: Arc<Mutex<PendingMap>>,
    _child: Arc<Mutex<Child>>,
}

impl Sidecar {
    pub async fn spawn() -> Result<Self> {
        let launch = resolve_paths()?;
        let (program, args_display): (PathBuf, String) = match &launch {
            SidecarLaunch::Frozen(path) => {
                tracing::info!(event = "sidecar_spawn_start", mode = "frozen", path = %path.display());
                (path.clone(), path.display().to_string())
            }
            SidecarLaunch::DevPython { python, script } => {
                tracing::info!(
                    event = "sidecar_spawn_start",
                    mode = "dev",
                    python = %python.display(),
                    script = %script.display(),
                );
                (python.clone(), format!("{} {}", python.display(), script.display()))
            }
        };

        let mut cmd = Command::new(&program);
        if let SidecarLaunch::DevPython { script, .. } = &launch {
            cmd.arg(script);
        }
        cmd
            // Force UTF-8 for all Python I/O so Japanese text survives the pipe
            // regardless of the Windows system codepage (cp932 default).
            .env("PYTHONUTF8", "1")
            .env("PYTHONIOENCODING", "utf-8")
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .kill_on_drop(true);

        let mut child = cmd
            .spawn()
            .with_context(|| format!("failed to spawn {}", args_display))?;
        let stdout = child
            .stdout
            .take()
            .ok_or_else(|| anyhow!("sidecar stdout not captured"))?;
        let stderr = child
            .stderr
            .take()
            .ok_or_else(|| anyhow!("sidecar stderr not captured"))?;
        let stdin = child
            .stdin
            .take()
            .ok_or_else(|| anyhow!("sidecar stdin not captured"))?;

        let pending: Arc<Mutex<PendingMap>> = Arc::new(Mutex::new(HashMap::new()));

        // stdout reader: correlate Responses to pending requests; log Events.
        {
            let pending = Arc::clone(&pending);
            tokio::spawn(async move {
                let mut lines = BufReader::new(stdout).lines();
                loop {
                    match lines.next_line().await {
                        Ok(Some(line)) => handle_stdout_line(&pending, &line).await,
                        Ok(None) => {
                            tracing::warn!(event = "sidecar_stdout_eof");
                            break;
                        }
                        Err(e) => {
                            tracing::error!(event = "sidecar_stdout_error", error = %e);
                            break;
                        }
                    }
                }
            });
        }

        // stderr drain: anything Python logs outside the protocol gets traced.
        tokio::spawn(async move {
            let mut lines = BufReader::new(stderr).lines();
            while let Ok(Some(line)) = lines.next_line().await {
                tracing::warn!(event = "sidecar_stderr", line = %line);
            }
        });

        tracing::info!(event = "sidecar_spawned");
        Ok(Self {
            stdin: Arc::new(Mutex::new(stdin)),
            pending,
            _child: Arc::new(Mutex::new(child)),
        })
    }

    /// Send a Request and await its matching Response. Returns the raw JSON
    /// payload so the caller can deserialize into a more specific shape.
    pub async fn send_request(
        &self,
        action: &str,
        params: Value,
        req_timeout_sec: f64,
    ) -> Result<Value> {
        let request_id = Uuid::new_v4().to_string();
        let (tx, rx) = oneshot::channel();
        self.pending.lock().await.insert(request_id.clone(), tx);

        let payload = OutgoingRequest {
            schema_version: PROTOCOL_SCHEMA_VERSION,
            request_id: request_id.clone(),
            action,
            params,
            timeout_sec: req_timeout_sec,
        };
        let mut line = serde_json::to_string(&payload).context("serialize Request")?;
        line.push('\n');

        {
            let mut stdin = self.stdin.lock().await;
            stdin
                .write_all(line.as_bytes())
                .await
                .context("write Request to sidecar stdin")?;
            stdin.flush().await.context("flush sidecar stdin")?;
        }

        tracing::debug!(event = "sidecar_request_sent", action, request_id);

        let wait = Duration::from_secs_f64(req_timeout_sec) + Duration::from_secs(REQUEST_TIMEOUT_GRACE_SEC);
        match timeout(wait, rx).await {
            Ok(Ok(resp)) => Ok(resp),
            Ok(Err(_)) => Err(anyhow!("sidecar response channel closed (process died?)")),
            Err(_) => {
                self.pending.lock().await.remove(&request_id);
                Err(anyhow!(
                    "sidecar did not respond within {req_timeout_sec}s (+{REQUEST_TIMEOUT_GRACE_SEC}s grace)"
                ))
            }
        }
    }
}

async fn handle_stdout_line(pending: &Arc<Mutex<PendingMap>>, line: &str) {
    let Ok(msg) = serde_json::from_str::<Value>(line) else {
        tracing::warn!(event = "sidecar_unparseable_line", line);
        return;
    };
    if let Some(id) = msg.get("request_id").and_then(|v| v.as_str()) {
        let sender = pending.lock().await.remove(id);
        match sender {
            Some(tx) => {
                let _ = tx.send(msg);
            }
            None => tracing::warn!(event = "sidecar_unpaired_response", request_id = id),
        }
        return;
    }
    if let Some(ev) = msg.get("event_type").and_then(|v| v.as_str()) {
        tracing::info!(event = "sidecar_event", event_type = ev);
        return;
    }
    tracing::warn!(event = "sidecar_unclassified_message", line);
}

/// What kind of sidecar is being launched — used to decide whether we pass a
/// ``script.py`` argument (dev) or just run the frozen ``sidecar.exe`` binary.
pub enum SidecarLaunch {
    Frozen(PathBuf),
    DevPython { python: PathBuf, script: PathBuf },
}

fn resolve_paths() -> Result<SidecarLaunch> {
    let exe = std::env::current_exe().context("current_exe unavailable")?;
    let exe_dir = exe
        .parent()
        .ok_or_else(|| anyhow!("cannot derive parent of {}", exe.display()))?;

    // Release / bundled layout. Tauri's bundler places declared resources
    // under a `resources/` subdir next to the installed exe on Windows.
    for candidate in [
        exe_dir.join("sidecar.exe"),
        exe_dir.join("resources").join("bin").join("sidecar.exe"),
        exe_dir.join("resources").join("sidecar.exe"),
    ] {
        if candidate.is_file() {
            return Ok(SidecarLaunch::Frozen(candidate));
        }
    }

    // Dev layout: C:\...\src-tauri\target\debug\aya-afi.exe → root is 3 up.
    let root = exe_dir
        .parent()
        .and_then(|p| p.parent())
        .and_then(|p| p.parent())
        .ok_or_else(|| anyhow!("cannot derive project root from {}", exe.display()))?;

    let python = root.join(".venv").join("Scripts").join("python.exe");
    let script = root.join("scripts").join("sidecar.py");
    if !python.exists() {
        return Err(anyhow!(
            "Python interpreter not found at {} (run `uv venv` then `uv pip install -e .`) \
             and no frozen sidecar.exe next to {}",
            python.display(),
            exe.display()
        ));
    }
    if !script.exists() {
        return Err(anyhow!("Sidecar script not found at {}", script.display()));
    }
    Ok(SidecarLaunch::DevPython { python, script })
}
