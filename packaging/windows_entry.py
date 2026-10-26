"""Keep worker dispatch ahead of Qt imports in the frozen executable."""

import multiprocessing

if __name__ == "__main__":
    multiprocessing.freeze_support()
    import logging

    try:
        from digital_child.app_paths import configure_packaged_app

        configure_packaged_app()
        from digital_child.desktop_app import main

        main()
    except Exception as exc:
        logging.exception("Desktop startup failed")
        import sys

        if sys.platform == "win32":
            import ctypes

            ctypes.windll.user32.MessageBoxW(
                None,
                "Не удалось запустить Digital Child. "
                "Подробности в каталоге logs внутри DIGITAL_CHILD_HOME "
                "(по умолчанию %LOCALAPPDATA%\\DigitalChild).",
                "Digital Child — ошибка запуска",
                0x10,
            )
        raise SystemExit(1) from exc
