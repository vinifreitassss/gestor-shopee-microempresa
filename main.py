from src.ui.app import GestorApp
from src.database import init_database


def main() -> None:
    init_database()
    app = GestorApp()
    app.mainloop()


if __name__ == "__main__":
    main()
