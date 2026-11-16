import argparse
import getpass
import sys

from sqlalchemy import text

from app.db.session import SessionLocal, engine
from app.services.auth_service import create_admin_user
from app.services.downstream_sync import AJClient, DownstreamService, ProviderError


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


def sync_downstream_command() -> int:
    # A separate connection retains this session-level lock while each waybill commits.
    with engine.connect() as lock_connection:
        if engine.dialect.name == "postgresql":
            locked = lock_connection.scalar(text("SELECT pg_try_advisory_lock(16001116)"))
            if not locked:
                print("同步任务已在运行")
                return 0
        try:
            with SessionLocal() as db:
                count = DownstreamService(db).run_due()
                print(f"已检查 {count} 张归属提单")
        finally:
            if engine.dialect.name == "postgresql":
                lock_connection.execute(text("SELECT pg_advisory_unlock(16001116)"))
                lock_connection.commit()
    return 0


def test_aj_command(awb: str | None) -> int:
    try:
        client = AJClient()
        result = client.ping()
        print(f"AJ 连接正常：{result.get('customer', '未知客户')}")
        if awb:
            shipment = client.fetch(awb)
            print(f"提单 {shipment.get('awb')}: {shipment.get('stage', {}).get('code')}")
    except ProviderError as exc:
        print(exc.detail, file=sys.stderr)
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Integrer backend management CLI")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("create-admin", help="Create the first admin account")
    subparsers.add_parser("sync-downstream", help="Poll assigned downstream waybills once")
    test_parser = subparsers.add_parser("test-aj", help="Check AJ credentials and optionally an AWB")
    test_parser.add_argument("--awb")
    args = parser.parse_args()

    if args.command == "create-admin":
        return create_admin_command()
    if args.command == "sync-downstream":
        return sync_downstream_command()
    if args.command == "test-aj":
        return test_aj_command(args.awb)

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

