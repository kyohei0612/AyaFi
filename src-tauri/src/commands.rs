//! Tauri invoke handlers. Thin layer: forward to sidecar or open OS resources.

use serde_json::{json, Value};
use tauri::State;
use tauri_plugin_opener::OpenerExt;

use crate::sidecar::Sidecar;

/// Rust-only smoke test. Returns a literal "pong" without touching the sidecar.
#[tauri::command]
pub fn ping() -> String {
    tracing::info!(event = "cmd_ping");
    "pong".to_string()
}

/// End-to-end smoke test: send a `ping` IPC Request to the Python sidecar.
#[tauri::command]
pub async fn sidecar_ping(
    sidecar: State<'_, Sidecar>,
    message: String,
) -> Result<Value, String> {
    tracing::info!(event = "cmd_sidecar_ping", message = %message);
    sidecar
        .send_request("ping", json!({ "message": message }), 10.0)
        .await
        .map_err(|e| e.to_string())
}

/// Resolve a product URL (Amazon / Rakuten) via the sidecar's affiliate layer
/// (ADR-002 F01-F02, Stage 2). Returns product info + affiliate click URL.
#[tauri::command]
pub async fn fetch_product(
    sidecar: State<'_, Sidecar>,
    url: String,
) -> Result<Value, String> {
    tracing::info!(event = "cmd_fetch_product", url = %url);
    sidecar
        .send_request("fetch_product", json!({ "url": url }), 15.0)
        .await
        .map_err(|e| e.to_string())
}

/// Validate generated content against SNS-specific algorithm rules
/// (Stage 4.a, currently Threads only).
#[tauri::command]
pub async fn validate_content(
    sidecar: State<'_, Sidecar>,
    sns: String,
    mode: String,
    body: String,
) -> Result<Value, String> {
    tracing::info!(event = "cmd_validate_content", sns = %sns, mode = %mode);
    sidecar
        .send_request(
            "validate_content",
            json!({ "sns": sns, "mode": mode, "body": body }),
            10.0,
        )
        .await
        .map_err(|e| e.to_string())
}

/// Generate an SNS post via the sidecar's LLM layer (ADR-004, Stage 1.d).
#[tauri::command]
pub async fn generate_post(
    sidecar: State<'_, Sidecar>,
    system_prompt: Option<String>,
    user_prompt: String,
    temperature: Option<f64>,
    max_output_tokens: Option<u32>,
) -> Result<Value, String> {
    tracing::info!(
        event = "cmd_generate_post",
        user_prompt_len = user_prompt.len(),
    );
    let mut params = json!({ "user_prompt": user_prompt });
    if let Some(s) = system_prompt {
        params["system_prompt"] = Value::String(s);
    }
    if let Some(t) = temperature {
        params["temperature"] = json!(t);
    }
    if let Some(m) = max_output_tokens {
        params["max_output_tokens"] = json!(m);
    }
    sidecar
        .send_request("generate_post", params, 60.0)
        .await
        .map_err(|e| e.to_string())
}

/// Publish a generated post to the chosen SNS (Stage 3.b).
#[tauri::command]
#[allow(non_snake_case)]
pub async fn publish_post(
    sidecar: State<'_, Sidecar>,
    sns: String,
    body: String,
    replyBody: Option<String>,
    imagePaths: Option<Vec<String>>,
    dryRun: Option<bool>,
) -> Result<Value, String> {
    tracing::info!(
        event = "cmd_publish_post",
        sns = %sns,
        char_count = body.chars().count(),
    );
    let mut params = json!({
        "sns": sns,
        "body": body,
        "image_paths": imagePaths.unwrap_or_default(),
        "dry_run": dryRun.unwrap_or(false),
    });
    if let Some(r) = replyBody {
        params["reply_body"] = Value::String(r);
    }
    sidecar
        .send_request("publish_post", params, 180.0)
        .await
        .map_err(|e| e.to_string())
}

/// Open the log directory in the OS file explorer (ADR-008).
#[tauri::command]
pub fn open_logs_dir(app: tauri::AppHandle) -> Result<(), String> {
    let logs = crate::logging::logs_dir();
    std::fs::create_dir_all(&logs).map_err(|e| e.to_string())?;
    let path = logs.to_string_lossy().to_string();
    app.opener()
        .open_path(path.clone(), None::<String>)
        .map_err(|e| e.to_string())?;
    tracing::info!(event = "cmd_open_logs_dir", path = %logs.display());
    Ok(())
}

/// Open note's new-post page in the user's default browser (ADR-006, case 3).
#[tauri::command]
pub fn open_note_compose(app: tauri::AppHandle) -> Result<(), String> {
    const URL: &str = "https://note.com/notes/new";
    app.opener()
        .open_url(URL.to_string(), None::<String>)
        .map_err(|e| e.to_string())?;
    tracing::info!(event = "cmd_open_note_compose", url = URL);
    Ok(())
}
