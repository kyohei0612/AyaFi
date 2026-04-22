// Prevents a console window from showing on Windows release builds.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod commands;
mod logging;
mod sidecar;

fn main() {
    logging::init();
    tracing::info!(event = "tauri_startup", "starting aya-afi shell");

    // Spawn Python sidecar before Tauri boots. If this fails we have no core
    // functionality, so surface the error immediately (Stage 1 design; Stage 3
    // will add auto-restart + degraded UI per ADR-010).
    let sidecar = tauri::async_runtime::block_on(sidecar::Sidecar::spawn())
        .expect("failed to spawn Python sidecar");

    tauri::Builder::default()
        .manage(sidecar)
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![
            commands::ping,
            commands::sidecar_ping,
            commands::fetch_product,
            commands::generate_post,
            commands::validate_content,
            commands::publish_post,
            commands::open_logs_dir,
            commands::open_note_compose,
        ])
        .setup(|_app| {
            tracing::info!(event = "tauri_setup_complete", "window ready");
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
