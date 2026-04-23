// Prevents a console window from showing on Windows release builds.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod commands;
mod logging;
mod sidecar;

fn main() {
    logging::init();
    tracing::info!(event = "tauri_startup", "starting aya-afi shell");

    // Spawn Python sidecar before Tauri boots. On failure we log the full
    // error AND surface a native message box, then exit — silent panics on
    // release builds (windows_subsystem="windows") leave the user with a
    // window that never appears and no explanation.
    let sidecar = match tauri::async_runtime::block_on(sidecar::Sidecar::spawn()) {
        Ok(s) => s,
        Err(e) => {
            tracing::error!(event = "sidecar_spawn_failed", error = %e);
            let msg = format!(
                "AyaFi のサイドカー (Python バックエンド) を起動できませんでした。\n\n{e}\n\n\
                 ログ: %APPDATA%\\AyaFi\\logs\\ で詳細確認してください。"
            );
            let _ = native_dialog::DialogBuilder::message()
                .set_level(native_dialog::MessageLevel::Error)
                .set_title("AyaFi 起動エラー")
                .set_text(&msg)
                .alert()
                .show();
            std::process::exit(1);
        }
    };

    tauri::Builder::default()
        .manage(sidecar)
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .plugin(tauri_plugin_process::init())
        .plugin(tauri_plugin_store::Builder::new().build())
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
