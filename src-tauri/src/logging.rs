//! Rust-side logging setup (mirrors ADR-008 for the Python sidecar).
//!
//! Output: `%APPDATA%/aya-afi/logs/tauri.log`, daily rotation, 30 days retention,
//! JSON format.

use std::path::PathBuf;
use tracing_appender::{non_blocking, rolling};
use tracing_subscriber::{fmt, prelude::*, EnvFilter};

const APP_NAME: &str = "aya-afi";
const BACKUP_DAYS: usize = 30;

pub fn user_data_dir() -> PathBuf {
    dirs::data_dir()
        .unwrap_or_else(|| PathBuf::from("."))
        .join(APP_NAME)
}

pub fn logs_dir() -> PathBuf {
    user_data_dir().join("logs")
}

pub fn init() {
    let dir = logs_dir();
    std::fs::create_dir_all(&dir).ok();

    let file_appender = rolling::Builder::new()
        .rotation(rolling::Rotation::DAILY)
        .filename_prefix("tauri")
        .filename_suffix("log")
        .max_log_files(BACKUP_DAYS)
        .build(&dir)
        .expect("failed to build rolling log appender");

    let (nb_writer, guard) = non_blocking(file_appender);
    // Keep the guard alive for the program lifetime.
    Box::leak(Box::new(guard));

    let filter = EnvFilter::try_from_default_env().unwrap_or_else(|_| EnvFilter::new("info"));

    tracing_subscriber::registry()
        .with(filter)
        .with(fmt::layer().json().with_writer(nb_writer))
        .init();
}
