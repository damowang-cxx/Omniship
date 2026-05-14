import argparse
import getpass
import sys

from app.db.session import SessionLocal
from app.services.auth_service import create_admin_user


def create_admin_command() -> int:
    email = input("管理员邮箱: ").strip()
    username = input("管理员用户名: ").strip()
    password = getpass.getpass("管理员密码: ")
    password_confirm = getpass.getpass("确认密码: ")

    if not email or not username:
        print("邮箱和用户名不能为空", file=sys.stderr)
        return 1
    if len(password) < 8:
        print("密码至少需要 8 位", file=sys.stderr)
        return 1
    if password != password_confirm:
        print("两次输入的密码不一致", file=sys.stderr)
        return 1

    with SessionLocal() as db:
        try:
            user = create_admin_user(
                db,
                email=email,
                username=username,
                password=password,
            )
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 1

    print(f"管理员已创建: {user.email}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Integrer backend management CLI")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("create-admin", help="Create the first admin account")
    args = parser.parse_args()

    if args.command == "create-admin":
        return create_admin_command()

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

