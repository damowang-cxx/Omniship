import asyncio
import logging
import re
import sys
from collections.abc import Sequence
from urllib.parse import urljoin

from playwright.async_api import Locator, Page, TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

from app.core.config import Settings, get_settings


logger = logging.getLogger(__name__)


class OmnishipScraperError(RuntimeError):
    pass


FIELD_BY_HEADER = {
    "number": "number",
    "status": "status",
    "statuschanged": "status_changed_at_raw",
    "weight(kg)": "weight_kg_raw",
    "received": "received_raw",
    "parcels": "parcels_raw",
    "inwarehouse": "in_warehouse_raw",
    "released": "released_raw",
    "outbound": "outbound_raw",
    "actions": "actions_raw",
}

EXPECTED_HEADERS = [
    "Number",
    "Status",
    "Status Changed",
    "Weight(kg)",
    "Received",
    "Parcels",
    "In Warehouse",
    "Released",
    "Out Bound",
    "Actions",
]

SUMMARY_HASH_FIELDS = [
    "number",
    "status",
    "weight_kg_raw",
    "received_raw",
    "parcels_raw",
    "in_warehouse_raw",
    "released_raw",
    "outbound_raw",
]

DETAIL_LABELS = {
    "waybill number",
    "waybill status",
    "uploaded on",
    "date received",
    "airline",
    "incoming flight",
    "arrived",
    "ground handler",
    "broker",
    "units",
    "units inbound",
    "units outbound",
    "pre-alert weight",
    "gross weight",
    "odd sized",
    "destinations",
    "units received",
    "total weight",
    "released",
}


def build_summary_hash(row: dict) -> str:
    import hashlib
    import json

    payload = {field: row.get(field) for field in SUMMARY_HASH_FIELDS}
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_detail_hash(detail: dict) -> str:
    import hashlib
    import json

    payload = {
        key: value
        for key, value in detail.items()
        if key not in {"scraped_at", "status_changed_raw"} and value not in (None, "")
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def normalize_header(value: str) -> str:
    return re.sub(r"\s+", "", value.strip().lower())


def normalize_cell_text(value: str, *, action_cell: bool = False) -> str | None:
    parts = [part.strip() for part in value.splitlines() if part.strip()]
    if not parts:
        return None
    separator = "; " if action_cell else " "
    return separator.join(parts)


class OmnishipScraper:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    async def scrape_air_waybills(self) -> list[dict]:
        return await self.scrape_air_waybill_summaries(mode="first_page")

    async def scrape_air_waybill_summaries(
        self,
        *,
        mode: str,
        existing_hashes: dict[str, str] | None = None,
        stop_after_unchanged: int | None = None,
    ) -> list[dict]:
        self._validate_credentials()
        if sys.platform == "win32":
            return await asyncio.to_thread(
                self._scrape_air_waybill_summaries_in_thread,
                mode,
                existing_hashes,
                stop_after_unchanged,
            )
        return await self._scrape_air_waybill_summaries_async(
            mode=mode,
            existing_hashes=existing_hashes,
            stop_after_unchanged=stop_after_unchanged,
        )

    def _scrape_air_waybill_summaries_in_thread(
        self,
        mode: str,
        existing_hashes: dict[str, str] | None,
        stop_after_unchanged: int | None,
    ) -> list[dict]:
        if hasattr(asyncio, "WindowsProactorEventLoopPolicy"):
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        return asyncio.run(
            self._scrape_air_waybill_summaries_async(
                mode=mode,
                existing_hashes=existing_hashes,
                stop_after_unchanged=stop_after_unchanged,
            )
        )

    async def _scrape_air_waybill_summaries_async(
        self,
        *,
        mode: str,
        existing_hashes: dict[str, str] | None,
        stop_after_unchanged: int | None,
    ) -> list[dict]:
        logger.info("Starting Chromium for Omniship Air Waybills %s scrape", mode)

        try:
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch(
                    headless=self.settings.playwright_headless
                )
                page = await browser.new_page()
                page.set_default_timeout(self.settings.playwright_timeout_ms)
                try:
                    await self._login(page)
                    await self._open_air_waybills(page)
                    await self._prepare_air_waybills_table(page)
                    rows = await self._extract_paginated_summaries(
                        page,
                        mode=mode,
                        existing_hashes=existing_hashes or {},
                        stop_after_unchanged=stop_after_unchanged
                        or self.settings.omniship_incremental_stop_after_unchanged,
                    )
                    logger.info(
                        "Omniship Air Waybills %s scrape succeeded: %s rows",
                        mode,
                        len(rows),
                    )
                    return rows
                finally:
                    await browser.close()
        except OmnishipScraperError:
            logger.exception("Omniship Air Waybills scrape failed")
            raise
        except PlaywrightTimeoutError as exc:
            logger.exception("Omniship Air Waybills scrape timed out")
            raise OmnishipScraperError("Page loading timed out") from exc
        except Exception as exc:
            logger.exception("Unexpected Omniship Air Waybills scrape failure")
            raise OmnishipScraperError(str(exc)) from exc

    async def scrape_waybill_details(self, rows: Sequence[dict]) -> list[dict]:
        self._validate_credentials()
        if sys.platform == "win32":
            return await asyncio.to_thread(self._scrape_waybill_details_in_thread, rows)
        return await self._scrape_waybill_details_async(rows)

    def _scrape_waybill_details_in_thread(self, rows: Sequence[dict]) -> list[dict]:
        if hasattr(asyncio, "WindowsProactorEventLoopPolicy"):
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        return asyncio.run(self._scrape_waybill_details_async(rows))

    async def _scrape_waybill_details_async(self, rows: Sequence[dict]) -> list[dict]:
        logger.info("Starting Chromium for %s Air Waybill detail pages", len(rows))

        try:
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch(
                    headless=self.settings.playwright_headless
                )
                page = await browser.new_page()
                page.set_default_timeout(self.settings.playwright_timeout_ms)
                try:
                    await self._login(page)
                    results: list[dict] = []
                    for row in rows:
                        number = row.get("number")
                        href = row.get("action_href")
                        if not number:
                            continue
                        if not href:
                            results.append(
                                {
                                    "number": number,
                                    "detail": None,
                                    "error": "Air Waybill action link not found",
                                }
                            )
                            continue
                        try:
                            logger.info("Opening Air Waybill detail page: %s", number)
                            await page.goto(href, wait_until="domcontentloaded")
                            await page.wait_for_load_state("networkidle")
                            if await self._has_password_input(page):
                                raise OmnishipScraperError(
                                    "Login failed or detail page redirected to login"
                                )
                            detail = await self._extract_detail_page(page, number)
                            results.append(
                                {"number": number, "detail": detail, "error": None}
                            )
                        except Exception as exc:
                            logger.exception(
                                "Air Waybill detail scrape failed: %s", number
                            )
                            results.append(
                                {"number": number, "detail": None, "error": str(exc)}
                            )
                    return results
                finally:
                    await browser.close()
        except OmnishipScraperError:
            raise
        except PlaywrightTimeoutError as exc:
            logger.exception("Omniship Air Waybill detail scrape timed out")
            raise OmnishipScraperError("Detail page loading timed out") from exc
        except Exception as exc:
            logger.exception("Unexpected Omniship Air Waybill detail scrape failure")
            raise OmnishipScraperError(str(exc)) from exc

    def _validate_credentials(self) -> None:
        if not self.settings.omniship_username or not self.settings.omniship_password:
            raise OmnishipScraperError(
                "OMNISHIP_USERNAME and OMNISHIP_PASSWORD must be configured"
            )

    async def _login(self, page: Page) -> None:
        logger.info("Opening Omniship login page")
        await page.goto(self.settings.omniship_login_url, wait_until="domcontentloaded")
        await page.wait_for_load_state("networkidle")

        await self._fill_first_available(
            page,
            [
                page.get_by_label(re.compile("email|username|user|账号|邮箱", re.I)),
                page.locator(
                    'input[type="email"], input[name*="email"], input[name*="username"], '
                    'input[name*="user"], input[id*="email"], input[id*="username"], '
                    'input[id*="user"]'
                ),
                page.locator('input[type="text"]').first,
            ],
            self.settings.omniship_username,
            "username",
        )
        await self._fill_first_available(
            page,
            [
                page.get_by_label(re.compile("password|密码", re.I)),
                page.locator('input[type="password"]'),
            ],
            self.settings.omniship_password,
            "password",
        )

        logger.info("Submitting Omniship login form")
        login_button = page.get_by_role(
            "button", name=re.compile("log in|login|sign in|登录|登入", re.I)
        )
        if await login_button.count():
            await login_button.first.click()
        else:
            submit_button = page.locator('button[type="submit"], input[type="submit"]')
            if not await submit_button.count():
                raise OmnishipScraperError("Login submit button not found")
            await submit_button.first.click()

        await page.wait_for_load_state("networkidle")
        if await self._has_extra_verification(page):
            raise OmnishipScraperError("Extra verification or captcha detected")

    async def _open_air_waybills(self, page: Page) -> None:
        logger.info("Opening Omniship Air Waybills page")
        await page.goto(
            self.settings.omniship_air_waybills_url,
            wait_until="domcontentloaded",
        )
        await page.wait_for_load_state("networkidle")

        if await self._has_password_input(page):
            raise OmnishipScraperError("Login failed or session was redirected to login")
        if await self._has_extra_verification(page):
            raise OmnishipScraperError("Extra verification or captcha detected")

    async def _prepare_air_waybills_table(self, page: Page) -> None:
        await self._set_rows_per_page(page, "25")
        await self._ensure_recent_activity_first(page)

    async def _set_rows_per_page(self, page: Page, value: str) -> None:
        logger.info("Setting Air Waybills rows per page to %s", value)

        select_candidates = [
            page.locator('select[aria-label*="Rows per page" i]'),
            page.locator("select"),
        ]
        for locator in select_candidates:
            if await locator.count():
                try:
                    await locator.first.select_option(value)
                    await page.wait_for_load_state("networkidle")
                    return
                except Exception:
                    logger.debug("Failed to use native rows-per-page select", exc_info=True)

        try:
            label = page.get_by_text(re.compile("Rows per page", re.I)).first
            if await label.count():
                pagination = label.locator(
                    "xpath=ancestor::*[contains(@class, 'MuiTablePagination') or "
                    "contains(@class, 'pagination') or contains(@class, 'Pagination')][1]"
                )
                container = pagination if await pagination.count() else page.locator("body")
                controls = [
                    container.get_by_role("combobox").first,
                    container.get_by_role("button", name=re.compile(r"^\s*\d+\s*$")).first,
                    container.locator('[role="button"]').first,
                ]
                for control in controls:
                    if await control.count() and await control.is_enabled():
                        await control.click()
                        option = page.get_by_role("option", name=re.compile(rf"^\s*{value}\s*$")).first
                        if await option.count():
                            await option.click()
                            await page.wait_for_load_state("networkidle")
                            return
        except Exception:
            logger.debug("Failed to set rows per page with custom control", exc_info=True)

        logger.warning("Could not confirm Air Waybills rows per page setting")

    async def _ensure_recent_activity_first(self, page: Page) -> None:
        current_order = await self._status_changed_order(page)
        if current_order == "recent_first":
            logger.info("Air Waybills already sorted by recent activity")
            return

        for _ in range(2):
            if not await self._click_status_changed_header(page):
                return
            await page.wait_for_load_state("networkidle")
            current_order = await self._status_changed_order(page)
            if current_order == "recent_first":
                logger.info("Air Waybills sorted by recent activity")
                return

        logger.warning("Could not confirm Status Changed recent-first sorting")

    async def _click_status_changed_header(self, page: Page) -> bool:
        table = page.locator("table").first
        if not await table.count():
            return False

        headers = await table.locator("thead tr th").all()
        if not headers:
            headers = await table.locator("tr").first.locator("th,td").all()

        for header in headers:
            text = await header.inner_text()
            if normalize_header(text) != "statuschanged":
                continue
            try:
                button = header.get_by_role("button").first
                if await button.count() and await button.is_enabled():
                    await button.click()
                else:
                    await header.click()
                return True
            except Exception:
                logger.debug("Failed to click Status Changed header", exc_info=True)
                return False

        logger.warning("Status Changed header not found for sorting")
        return False

    async def _status_changed_order(self, page: Page) -> str | None:
        try:
            rows = await self._extract_table(page)
        except Exception:
            logger.debug("Could not inspect Status Changed order", exc_info=True)
            return None

        ages = [
            self._parse_status_changed_age_seconds(row.get("status_changed_at_raw"))
            for row in rows
        ]
        ages = [age for age in ages if age is not None]
        if len(ages) < 2:
            return None
        return "recent_first" if ages[0] <= ages[-1] else "oldest_first"

    def _parse_status_changed_age_seconds(self, value: str | None) -> int | None:
        if not value:
            return None

        normalized = value.strip().lower()
        if not normalized:
            return None
        if "just now" in normalized:
            return 0
        if normalized in {"yesterday"} or normalized.startswith("yesterday "):
            return 24 * 60 * 60

        words = {
            "a": 1,
            "an": 1,
            "one": 1,
        }
        units = {
            "second": 1,
            "minute": 60,
            "hour": 60 * 60,
            "day": 24 * 60 * 60,
            "week": 7 * 24 * 60 * 60,
            "month": 30 * 24 * 60 * 60,
            "year": 365 * 24 * 60 * 60,
        }
        match = re.search(
            r"(\d+|a|an|one)\s+"
            r"(second|minute|hour|day|week|month|year)s?\s+ago",
            normalized,
        )
        if match:
            amount = words.get(match.group(1), int(match.group(1)) if match.group(1).isdigit() else 1)
            return amount * units[match.group(2)]

        return None

    async def _extract_paginated_summaries(
        self,
        page: Page,
        *,
        mode: str,
        existing_hashes: dict[str, str],
        stop_after_unchanged: int,
    ) -> list[dict]:
        all_rows: list[dict] = []
        unchanged_streak = 0
        page_index = 1

        while True:
            rows = await self._extract_table(page)
            all_rows.extend(rows)
            pagination = await self._read_pagination(page)
            logger.info(
                "Read Air Waybills page %s: %s rows%s",
                page_index,
                len(rows),
                f", pagination={pagination}" if pagination else "",
            )

            if mode == "first_page":
                break

            if mode == "incremental":
                for row in rows:
                    existing_hash = existing_hashes.get(row.get("number") or "")
                    if existing_hash and existing_hash == build_summary_hash(row):
                        unchanged_streak += 1
                    else:
                        unchanged_streak = 0
                    if unchanged_streak >= stop_after_unchanged:
                        logger.info(
                            "Stopping incremental scrape after %s unchanged rows",
                            unchanged_streak,
                        )
                        return all_rows

            if pagination and pagination["end"] >= pagination["total"]:
                break
            if not await self._go_to_next_page(page):
                break
            page_index += 1

        return all_rows

    async def _extract_table(self, page: Page) -> list[dict]:
        logger.info("Waiting for Air Waybills table")
        table = page.locator("table").first
        try:
            await table.wait_for(state="visible")
        except PlaywrightTimeoutError as exc:
            raise OmnishipScraperError("Air Waybills table not found") from exc

        header_texts = await self._read_headers(table)
        column_map = self._build_column_map(header_texts)
        rows = await self._read_body_rows(table)
        logger.info("Air Waybills table found with %s data rows", len(rows))
        return await self._rows_to_dicts(page, rows, column_map)

    async def _read_headers(self, table: Locator) -> list[str]:
        headers = await table.locator("thead tr th").all_inner_texts()
        if not headers:
            first_row_headers = table.locator("tr").first.locator("th,td")
            headers = await first_row_headers.all_inner_texts()
        if not headers:
            raise OmnishipScraperError("Air Waybills table headers not found")
        return [header.strip() for header in headers]

    def _build_column_map(self, headers: Sequence[str]) -> dict[str, int]:
        normalized_to_index = {
            normalize_header(header): index for index, header in enumerate(headers)
        }
        missing = [
            header
            for header in EXPECTED_HEADERS
            if normalize_header(header) not in normalized_to_index
        ]
        if missing:
            raise OmnishipScraperError(
                f"Air Waybills table missing expected columns: {', '.join(missing)}"
            )
        return {
            FIELD_BY_HEADER[normalize_header(header)]: normalized_to_index[
                normalize_header(header)
            ]
            for header in EXPECTED_HEADERS
        }

    async def _read_body_rows(self, table: Locator) -> list[Locator]:
        rows = await table.locator("tbody tr").all()
        if rows:
            return rows

        all_rows = await table.locator("tr").all()
        if len(all_rows) <= 1:
            return []
        return all_rows[1:]

    async def _rows_to_dicts(
        self, page: Page, rows: Sequence[Locator], column_map: dict[str, int]
    ) -> list[dict]:
        result: list[dict] = []
        for row in rows:
            cells = await row.locator("td").all()
            if not cells:
                continue
            record: dict[str, str | None] = {}
            for field_name, index in column_map.items():
                if index >= len(cells):
                    raise OmnishipScraperError(
                        "Air Waybills row has fewer cells than expected columns"
                    )
                text = await cells[index].inner_text()
                record[field_name] = normalize_cell_text(
                    text, action_cell=field_name == "actions_raw"
                )
                if field_name == "actions_raw":
                    link = cells[index].locator("a[href]").first
                    if await link.count():
                        href = await link.get_attribute("href")
                        record["action_href"] = urljoin(page.url, href) if href else None
            if record.get("number"):
                result.append(record)
        return result

    async def _read_pagination(self, page: Page) -> dict[str, int] | None:
        body_text = await page.locator("body").inner_text()
        matches = re.findall(
            r"([\d,]+)\s*[-–—]\s*([\d,]+)\s+of\s+([\d,]+)", body_text
        )
        if not matches:
            return None
        start, end, total = matches[-1]
        return {
            "start": int(start.replace(",", "")),
            "end": int(end.replace(",", "")),
            "total": int(total.replace(",", "")),
        }

    async def _go_to_next_page(self, page: Page) -> bool:
        candidates = [
            page.get_by_role("button", name=re.compile("next|go to next|›|>", re.I)),
            page.locator('button[aria-label*="next" i]'),
            page.locator('a[aria-label*="next" i]'),
            page.locator('button[title*="next" i]'),
            page.locator('button:has-text("›")'),
            page.locator('button:has-text(">")'),
        ]

        for locator in candidates:
            count = await locator.count()
            if not count:
                continue
            candidate = locator.last
            try:
                if not await candidate.is_enabled():
                    continue
                await candidate.click()
                await page.wait_for_load_state("networkidle")
                return True
            except Exception:
                logger.debug("Failed to click next pagination candidate", exc_info=True)

        logger.info("No enabled next pagination control found")
        return False

    async def _extract_detail_page(self, page: Page, fallback_number: str) -> dict:
        body_text = await page.locator("body").inner_text()
        lines = [line.strip() for line in body_text.splitlines() if line.strip()]
        number = self._extract_label_value(lines, "Waybill Number") or fallback_number

        detail = {
            "waybill_number": number,
            "waybill_status": self._extract_label_value(lines, "Waybill Status"),
            "uploaded_on_raw": self._extract_label_value(lines, "Uploaded On"),
            "date_received_raw": self._extract_label_value(lines, "Date Received"),
            "airline_raw": self._extract_label_value(lines, "Airline"),
            "incoming_flight_raw": self._extract_label_value(lines, "Incoming flight"),
            "arrived_raw": self._extract_label_value(lines, "Arrived"),
            "ground_handler_raw": self._extract_label_value(lines, "Ground Handler"),
            "broker_raw": self._extract_label_value(lines, "Broker"),
            "units_raw": self._extract_label_value(lines, "Units"),
            "units_inbound_raw": self._extract_label_value(lines, "Units Inbound"),
            "units_outbound_raw": self._extract_label_value(lines, "Units outbound"),
            "pre_alert_weight_raw": self._extract_label_value(
                lines, "Pre-Alert Weight"
            ),
            "gross_weight_raw": self._extract_label_value(lines, "Gross Weight"),
            "odd_sized_raw": self._extract_label_value(lines, "Odd Sized"),
            "destinations": self._extract_destinations(lines),
        }

        if not detail["waybill_number"]:
            raise OmnishipScraperError("Waybill detail page number not found")
        return detail

    def _extract_label_value(self, lines: Sequence[str], label: str) -> str | None:
        normalized_label = self._normalize_detail_label(label)
        for index, line in enumerate(lines):
            same_line = re.match(rf"^{re.escape(label)}\s*[:：]\s*(.+)$", line, re.I)
            if same_line:
                return same_line.group(1).strip() or None

            normalized_line = self._normalize_detail_label(line)
            if normalized_line == normalized_label:
                return self._next_non_label_value(lines, index + 1)

            if normalized_line not in DETAIL_LABELS:
                inline_value = re.match(rf"^{re.escape(label)}\s+(.+)$", line, re.I)
                if inline_value:
                    return inline_value.group(1).strip() or None
        return None

    def _next_non_label_value(self, lines: Sequence[str], start_index: int) -> str | None:
        for line in lines[start_index:]:
            normalized = self._normalize_detail_label(line)
            if line.endswith(":") or normalized in DETAIL_LABELS:
                return None
            return line
        return None

    def _extract_destinations(self, lines: Sequence[str]) -> list[dict]:
        try:
            start_index = next(
                index
                for index, line in enumerate(lines)
                if self._normalize_detail_label(line) == "destinations"
            )
        except StopIteration:
            return []

        metric_fields = {
            "units received": "units_received_raw",
            "units outbound": "units_outbound_raw",
            "total weight": "total_weight_raw",
            "released": "released_raw",
        }
        destinations: list[dict] = []
        index = start_index + 1

        while index < len(lines):
            line = lines[index]
            normalized = self._normalize_detail_label(line)
            if normalized in metric_fields:
                index += 1
                continue

            destination = {"name": line}
            index += 1
            if index < len(lines):
                maybe_country = lines[index]
                if self._normalize_detail_label(maybe_country) not in metric_fields:
                    destination["country"] = maybe_country
                    index += 1

            while index < len(lines):
                metric_line = lines[index]
                metric_label = self._normalize_detail_label(metric_line)
                if metric_label not in metric_fields:
                    break
                value = self._value_after_metric_line(metric_line)
                if value is None:
                    value = self._next_non_label_value(lines, index + 1)
                    index += 1
                destination[metric_fields[metric_label]] = value
                index += 1

            destinations.append(destination)

        return [destination for destination in destinations if destination.get("name")]

    def _value_after_metric_line(self, line: str) -> str | None:
        match = re.match(r"^.+?[:：]\s*(.+)$", line)
        if not match:
            return None
        return match.group(1).strip() or None

    def _normalize_detail_label(self, value: str) -> str:
        label = re.split(r"[:：]", value.strip(), maxsplit=1)[0]
        return re.sub(r"\s+", " ", label.rstrip(":：").lower())

    async def _fill_first_available(
        self,
        page: Page,
        locators: Sequence[Locator],
        value: str,
        field_label: str,
    ) -> None:
        for locator in locators:
            candidate = locator.first
            if await candidate.count():
                try:
                    await candidate.fill(value)
                    return
                except Exception:
                    logger.debug("Failed to fill %s candidate", field_label, exc_info=True)
        raise OmnishipScraperError(f"Login {field_label} field not found")

    async def _has_password_input(self, page: Page) -> bool:
        return await page.locator('input[type="password"]').count() > 0

    async def _has_extra_verification(self, page: Page) -> bool:
        verification = page.get_by_text(
            re.compile("captcha|verification|verify|验证码|验证", re.I)
        )
        return await verification.count() > 0
