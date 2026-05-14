import asyncio
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from playwright.async_api import Locator, Page, TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

from app.core.config import Settings, get_settings
from app.db.models import WaybillUpload
from app.repositories.waybill_user_binding_repository import normalize_waybill_number
from app.services.omniship_scraper import OmnishipScraper, OmnishipScraperError


logger = logging.getLogger(__name__)


class AllineWaybillUploadError(RuntimeError):
    pass


class AllineWaybillUploader:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.scraper = OmnishipScraper(self.settings)

    async def submit_upload(self, upload: WaybillUpload) -> None:
        self.scraper._validate_credentials()
        if sys.platform == "win32":
            return await asyncio.to_thread(self._submit_upload_in_thread, upload)
        return await self._submit_upload_async(upload)

    def _submit_upload_in_thread(self, upload: WaybillUpload) -> None:
        if hasattr(asyncio, "WindowsProactorEventLoopPolicy"):
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        return asyncio.run(self._submit_upload_async(upload))

    async def _submit_upload_async(self, upload: WaybillUpload) -> None:
        document_paths, pre_alert_path = self._resolve_upload_files(upload)
        logger.info("Starting ALLINE waybill upload: %s", upload.air_waybill_number)

        try:
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch(
                    headless=self.settings.playwright_headless
                )
                page = await browser.new_page()
                page.set_default_timeout(self.settings.playwright_timeout_ms)
                try:
                    await self.scraper._login(page)
                    await self._open_create_page(page)
                    await self._complete_create_waybill_step(
                        page,
                        upload=upload,
                        document_paths=document_paths,
                    )
                    await self._complete_pre_alert_step(page, pre_alert_path)
                    await self._complete_map_fields_step(page)
                    await self._complete_preview_step(page)
                    await self._verify_waybill_created(page, upload.air_waybill_number)
                    logger.info("ALLINE waybill upload succeeded: %s", upload.air_waybill_number)
                except Exception:
                    await self._save_failure_artifacts(page, upload)
                    raise
                finally:
                    await browser.close()
        except AllineWaybillUploadError:
            logger.exception("ALLINE waybill upload failed: %s", upload.air_waybill_number)
            raise
        except OmnishipScraperError as exc:
            logger.exception("ALLINE login failed before upload")
            raise AllineWaybillUploadError(str(exc)) from exc
        except PlaywrightTimeoutError as exc:
            logger.exception("ALLINE waybill upload timed out: %s", upload.air_waybill_number)
            raise AllineWaybillUploadError("ALLINE upload page timed out") from exc
        except Exception as exc:
            logger.exception("Unexpected ALLINE waybill upload failure")
            raise AllineWaybillUploadError(str(exc)) from exc

    def _resolve_upload_files(self, upload: WaybillUpload) -> tuple[list[str], str]:
        document_paths = [
            file.storage_path
            for file in upload.files
            if file.file_kind == "air_waybill_document"
        ]
        pre_alert_paths = [
            file.storage_path
            for file in upload.files
            if file.file_kind == "customer_pre_alert"
        ]
        if not document_paths:
            raise AllineWaybillUploadError("Air Waybill Document(s) file not found")
        if not pre_alert_paths:
            raise AllineWaybillUploadError("Customer Pre Alert file not found")

        paths = [*document_paths, pre_alert_paths[0]]
        for path in paths:
            if not Path(path).is_file():
                raise AllineWaybillUploadError(f"Upload file is missing: {Path(path).name}")
        return document_paths, pre_alert_paths[0]

    async def _open_create_page(self, page: Page) -> None:
        logger.info("Opening ALLINE create Air Waybill page")
        await page.goto(
            self.settings.omniship_air_waybills_create_url,
            wait_until="domcontentloaded",
        )
        await page.wait_for_load_state("networkidle")
        if await self.scraper._has_password_input(page):
            raise AllineWaybillUploadError("Login failed or create page redirected to login")
        if await self.scraper._has_extra_verification(page):
            raise AllineWaybillUploadError("Extra verification or captcha detected")

    async def _complete_create_waybill_step(
        self,
        page: Page,
        *,
        upload: WaybillUpload,
        document_paths: list[str],
    ) -> None:
        logger.info("Completing ALLINE Create Waybill step: %s", upload.air_waybill_number)
        await self._choose_option(page, "Shipment Type", upload.shipment_type)
        form = page.locator("form#air_waybill_create")
        await form.wait_for(state="visible")
        await self._fill_create_waybill_core_fields(form, upload)
        if upload.arrival_flight_number:
            await self._fill_create_waybill_arrival_flight(
                form,
                upload.arrival_flight_number,
            )
        await self._set_create_waybill_document(form, document_paths)
        await self._click_button(page, [r"^next$", r"next"], "Create Waybill next button")
        await self._wait_for_step_visible(page, "step-2", "Create Waybill")

    async def _complete_pre_alert_step(self, page: Page, pre_alert_path: str) -> None:
        logger.info("Completing ALLINE Upload Pre Alert File step")
        await page.wait_for_load_state("networkidle")
        await self._wait_for_step_visible(page, "step-2", "Create Waybill")
        await self._upload_pre_alert_dropzone(page, pre_alert_path)
        await self._wait_for_dropzone_upload(page)
        await self._click_button(page, [r"^next$", r"next"], "Pre Alert next button")
        await self._wait_for_step_visible(page, "step-3", "Upload Pre Alert File")

    async def _complete_map_fields_step(self, page: Page) -> None:
        logger.info("Completing ALLINE Map Fields step")
        await self._wait_for_step_visible(page, "step-3", "Upload Pre Alert File")
        await page.wait_for_load_state("networkidle")
        await self._wait_for_map_fields_ready(page)
        await self._map_pre_alert_fields(page)
        await self._save_mapping_if_available(page)
        await self._click_button(page, [r"^next$", r"next"], "Map Fields next button")
        await self._wait_for_step_visible(page, "step-4", "Map Fields")

    async def _complete_preview_step(self, page: Page) -> None:
        logger.info("Completing ALLINE Preview and confirm step")
        await self._wait_for_step_visible(page, "step-4", "Map Fields")
        await page.wait_for_load_state("networkidle")
        await self._wait_for_preview_validation(page)
        counts = await self._get_preview_record_counts(page)
        if counts is not None:
            ready_count, total_count = counts
            if total_count == 0:
                raise AllineWaybillUploadError(
                    "ALLINE preview imported 0 records from the Pre Alert file"
                )
            if ready_count <= 0:
                await self._raise_page_error_if_present(page)
                raise AllineWaybillUploadError(
                    f"ALLINE preview has 0 of {total_count} records ready to import"
                )
        await self._click_button(
            page,
            [r"upload\s+\d+\s+records", r"upload.*records", r"^upload$"],
            "Upload records button",
        )
        try:
            await page.wait_for_url(
                re.compile(r".*/air_waybills/?(?:\?.*)?$"),
                wait_until="networkidle",
                timeout=self.settings.playwright_timeout_ms,
            )
        except PlaywrightTimeoutError:
            await self._raise_page_error_if_present(page)
            raise

    async def _wait_for_preview_validation(self, page: Page) -> None:
        timeout_ms = max(
            self.settings.playwright_timeout_ms,
            self.settings.alline_preview_validation_timeout_ms,
        )
        try:
            await page.wait_for_function(
                """
                () => {
                  const step = document.querySelector("#step-4");
                  if (!step) return false;
                  const text = step.innerText || "";
                  const isLoading = Boolean(
                    step.querySelector(".panel-loading, .panel-loader, .loading-text")
                  ) || /preparing\\s+for\\s+validation/i.test(text);
                  const hasUploadButton = Array.from(step.querySelectorAll("button"))
                    .some((button) => /upload\\s+\\d+\\s+records/i.test(button.innerText || ""));
                  const hasResolvedCounts =
                    /\\d+\\s+of\\s+\\d+\\s+records\\s+are\\s+ready\\s+to\\s+be\\s+imported/i.test(text) &&
                    !isLoading;
                  return hasUploadButton || hasResolvedCounts;
                }
                """,
                timeout=timeout_ms,
            )
        except PlaywrightTimeoutError as exc:
            state = await self._get_preview_state(page)
            raise AllineWaybillUploadError(
                "ALLINE preview validation did not finish"
                + (f" ({state})" if state else "")
            ) from exc

        state = await self._get_preview_state(page)
        logger.info("ALLINE preview validation finished: %s", state or "ready")

    async def _get_preview_state(self, page: Page) -> str:
        try:
            return await page.locator("#step-4").first.evaluate(
                """
                (step) => {
                  const text = (step.innerText || "").replace(/\\s+/g, " ").trim();
                  const hasLoading = Boolean(
                    step.querySelector(".panel-loading, .panel-loader, .loading-text")
                  );
                  const uploadButtons = Array.from(step.querySelectorAll("button"))
                    .map((button) => button.innerText?.replace(/\\s+/g, " ").trim())
                    .filter(Boolean);
                  return [
                    hasLoading ? "loading" : "not loading",
                    text.slice(0, 240),
                    uploadButtons.length ? `buttons: ${uploadButtons.join("; ")}` : "",
                  ].filter(Boolean).join(" | ");
                }
                """
            )
        except Exception:
            logger.debug("Failed to read ALLINE preview state", exc_info=True)
            return ""

    async def _verify_waybill_created(self, page: Page, number: str) -> None:
        logger.info("Verifying ALLINE waybill appears in list: %s", number)
        await page.goto(self.settings.omniship_air_waybills_url, wait_until="domcontentloaded")
        await page.wait_for_load_state("networkidle")
        try:
            await self.scraper._prepare_air_waybills_table(page)
        except Exception:
            logger.debug("Could not prepare Air Waybills table for upload verification", exc_info=True)

        body_text = await page.locator("body").inner_text()
        normalized_target = normalize_waybill_number(number)
        if number in body_text or normalized_target in normalize_waybill_number(body_text):
            return
        raise AllineWaybillUploadError(
            "ALLINE upload finished but Air Waybill Number was not found in list"
        )

    async def _choose_option(self, page: Page, label: str, value: str) -> None:
        escaped_value = re.escape(value)
        candidates = [
            page.get_by_role("radio", name=re.compile(rf"^\s*{escaped_value}\s*$", re.I)),
            page.get_by_label(re.compile(rf"^\s*{escaped_value}\s*$", re.I)),
        ]
        for locator in candidates:
            candidate = locator.first
            if await candidate.count():
                try:
                    await candidate.check()
                    return
                except Exception:
                    try:
                        await candidate.click()
                        return
                    except Exception:
                        logger.debug("Failed to choose %s option candidate", label, exc_info=True)

        label_pattern = re.compile(label, re.I)
        labeled_control = page.get_by_label(label_pattern).first
        if await labeled_control.count():
            try:
                await labeled_control.select_option(label=value)
                return
            except Exception:
                try:
                    await labeled_control.select_option(value=value)
                    return
                except Exception:
                    logger.debug("Failed to select %s by labeled control", label, exc_info=True)
            try:
                await labeled_control.click()
                if await self._click_visible_option(page, value):
                    return
            except Exception:
                logger.debug("Failed to open %s labeled control", label, exc_info=True)

        if await self._open_control_near_label(page, label_pattern):
            if await self._click_visible_option(page, value):
                return

        if await self._click_visible_option(page, value):
            return

        raise AllineWaybillUploadError(f"{label} option not found: {value}")

    async def _open_control_near_label(self, page: Page, label_pattern: re.Pattern) -> bool:
        label_node = page.get_by_text(label_pattern).first
        if not await label_node.count():
            return False

        containers = [
            label_node.locator("xpath=ancestor::label[1]"),
            label_node.locator("xpath=ancestor::div[1]"),
            label_node.locator("xpath=ancestor::div[2]"),
        ]
        for container in containers:
            if not await container.count():
                continue
            controls = [
                container.get_by_role("combobox").first,
                container.locator('[role="button"]').first,
                container.locator("select").first,
                container.locator("input").first,
            ]
            for control in controls:
                if not await control.count():
                    continue
                try:
                    await control.click()
                    return True
                except Exception:
                    logger.debug("Failed to open option control near label", exc_info=True)
        return False

    async def _click_visible_option(self, page: Page, value: str) -> bool:
        escaped_value = re.escape(value)
        option_candidates = [
            page.get_by_role("option", name=re.compile(rf"^\s*{escaped_value}\s*$", re.I)),
            page.get_by_role("menuitem", name=re.compile(rf"^\s*{escaped_value}\s*$", re.I)),
            page.locator(f'[role="listbox"] >> text=/^\\s*{escaped_value}\\s*$/i'),
            page.get_by_text(re.compile(rf"^\s*{escaped_value}\s*$", re.I)),
        ]
        for locator in option_candidates:
            candidate = locator.first
            if not await candidate.count():
                continue
            try:
                await candidate.click()
                return True
            except Exception:
                logger.debug("Failed to click option candidate: %s", value, exc_info=True)
        return False

    async def _wait_for_map_fields_ready(self, page: Page) -> None:
        try:
            await page.wait_for_function(
                """
                () => {
                  const bodyText = document.body?.innerText?.toLowerCase() || "";
                  const visibleControls = Array.from(
                    document.querySelectorAll(
                      "select, [role='combobox'], input:not([type='hidden']):not([type='file'])"
                    )
                  ).filter((element) => {
                    const style = window.getComputedStyle(element);
                    return style.display !== "none" &&
                      style.visibility !== "hidden" &&
                      !element.disabled;
                  });
                  return visibleControls.length > 0 ||
                    /preview|confirm|upload\\s+\\d*\\s*records/.test(bodyText);
                }
                """,
                timeout=min(self.settings.playwright_timeout_ms, 10_000),
            )
        except PlaywrightTimeoutError:
            logger.debug("Map Fields controls did not become visible before timeout")

    async def _map_pre_alert_fields(self, page: Page) -> None:
        field_aliases = {
            "air waybill number": [
                "air waybill number",
                "awb number",
                "waybill number",
                "number",
            ],
            "gross weight": [
                "gross weight",
                "gross weight kg",
                "gross weight (kg)",
                "air waybill gross weight",
                "air waybill gross weight kg",
                "weight",
                "weight kg",
                "total weight",
            ],
            "pieces": [
                "pieces",
                "piece",
                "pcs",
                "parcels",
                "units",
            ],
        }

        for field_name, aliases in field_aliases.items():
            mapped = await self._map_native_select_by_aliases(page, aliases)
            if mapped:
                logger.info("Mapped ALLINE pre-alert field: %s", field_name)

    async def _save_mapping_if_available(self, page: Page) -> None:
        step = page.locator("#step-3").first
        save_button = step.get_by_role(
            "button",
            name=re.compile(r"save\s+mapping", re.I),
        ).first
        if not await save_button.count():
            return
        try:
            if await save_button.is_enabled():
                await save_button.click()
                await page.wait_for_load_state("networkidle")
                try:
                    await page.get_by_text(
                        re.compile(r"mapping\s+was\s+successfully\s+saved", re.I)
                    ).wait_for(
                        state="attached",
                        timeout=min(self.settings.playwright_timeout_ms, 5_000),
                    )
                except PlaywrightTimeoutError:
                    logger.debug("Save Mapping success message was not observed")
        except AllineWaybillUploadError:
            raise
        except Exception as exc:
            logger.debug("Failed to save ALLINE mapping", exc_info=True)
            raise AllineWaybillUploadError("Save Mapping button failed") from exc

    async def _get_preview_record_counts(self, page: Page) -> tuple[int, int] | None:
        text_candidates = [
            page.locator("#step-4 .v-alert__content").first,
            page.locator("#step-4").first,
        ]
        for locator in text_candidates:
            if not await locator.count():
                continue
            text = await locator.inner_text()
            match = re.search(
                r"(\d+)\s+of\s+(\d+)\s+records\s+are\s+ready\s+to\s+be\s+imported",
                re.sub(r"\s+", " ", text),
                re.I,
            )
            if match:
                return int(match.group(1)), int(match.group(2))
        return None

    async def _map_native_select_by_aliases(
        self,
        page: Page,
        aliases: list[str],
    ) -> bool:
        selects = page.locator("select")
        count = await selects.count()
        mapped = False
        for index in range(count):
            select = selects.nth(index)
            try:
                if not await select.is_visible() or not await select.is_enabled():
                    continue
                context_text = await select.evaluate(
                    """
                    (element) => {
                      const container = element.closest(
                        "tr, [role='row'], label, fieldset, .row, .form-group, .field, div"
                      );
                      return container?.innerText || element.parentElement?.innerText || "";
                    }
                    """
                )
                options = await select.locator("option").all_text_contents()
                selected_option = self._find_alias_match(options, aliases)
                if not selected_option:
                    continue

                current_value = await select.input_value()
                context_matches = self._text_matches_alias(context_text, aliases)
                select_is_unmapped = not current_value or self._text_matches_alias(
                    current_value,
                    ["select", "choose", "please select", "none", "-"],
                )
                if context_matches or select_is_unmapped:
                    await select.select_option(label=selected_option)
                    mapped = True
            except Exception:
                logger.debug("Failed to map native select candidate", exc_info=True)
        return mapped

    def _find_alias_match(self, values: list[str], aliases: list[str]) -> str | None:
        for value in values:
            if self._text_matches_alias(value, aliases):
                return value
        return None

    def _text_matches_alias(self, text: str | None, aliases: list[str]) -> bool:
        normalized_text = self._normalize_mapping_text(text or "")
        if not normalized_text:
            return False
        return any(
            self._normalize_mapping_text(alias) in normalized_text
            for alias in aliases
        )

    def _normalize_mapping_text(self, text: str) -> str:
        return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()

    async def _fill_create_waybill_core_fields(
        self,
        form: Locator,
        upload: WaybillUpload,
    ) -> None:
        row = form.locator(".form-group.row").filter(
            has_text=re.compile(r"Air\s+Waybill\s+Number", re.I)
        ).first
        await row.wait_for(state="visible")
        inputs = row.locator(
            'input.form-control:not([type="hidden"]):not([type="file"])'
        )
        if await inputs.count() < 3:
            raise AllineWaybillUploadError("Create Waybill core fields not found")

        await self._fill_exact_input(
            inputs.nth(0),
            "Air Waybill Number",
            upload.air_waybill_number,
        )
        await self._fill_exact_input(
            inputs.nth(1),
            "Air Waybill Gross Weight",
            self._format_decimal_for_input(upload.gross_weight_kg),
        )
        await self._fill_exact_input(
            inputs.nth(2),
            "Air Waybill Pieces",
            str(upload.pieces),
        )

    async def _fill_create_waybill_arrival_flight(
        self,
        form: Locator,
        value: str,
    ) -> None:
        row = form.locator(".form-group.row").filter(
            has_text=re.compile(r"Arrival\s+Flight\s+Number", re.I)
        ).first
        if await row.count():
            await self._fill_exact_input(
                row.locator('input.form-control:not([type="hidden"])').first,
                "Arrival Flight Number",
                value,
            )

    async def _set_create_waybill_document(
        self,
        form: Locator,
        paths: list[str],
    ) -> None:
        file_input = form.locator(
            'input[type="file"][placeholder*="Waybill" i], input[type="file"]'
        ).first
        if not await file_input.count():
            raise AllineWaybillUploadError("Air Waybill Document(s) file input not found")
        await file_input.set_input_files(paths)

    async def _fill_exact_input(
        self,
        locator: Locator,
        label: str,
        value: str,
    ) -> None:
        await locator.wait_for(state="visible")
        if not await locator.is_enabled():
            raise AllineWaybillUploadError(f"{label} field is disabled")
        await locator.fill(value)
        await locator.dispatch_event("input")
        await locator.dispatch_event("change")

    def _format_decimal_for_input(self, value) -> str:
        text = format(value, "f") if hasattr(value, "__format__") else str(value)
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return text or "0"

    async def _fill_labeled_input(
        self,
        page: Page,
        label: str,
        value: str,
        *,
        css_fallback: str,
        required: bool = True,
    ) -> bool:
        label_pattern = self._label_pattern(label)
        locators = [
            page.get_by_label(label_pattern),
            page.get_by_placeholder(label_pattern),
            page.get_by_role("textbox", name=label_pattern),
            page.get_by_role("spinbutton", name=label_pattern),
        ]

        for locator in locators:
            if await self._try_fill_locator(locator, label, value):
                return True

        if await self._fill_input_near_label(page, label_pattern, label, value):
            return True

        if await self._try_fill_locator(
            page.locator(css_fallback),
            label,
            value,
        ):
            return True

        if required:
            raise AllineWaybillUploadError(f"{label} field not found")
        return False

    async def _fill_air_waybill_number(self, page: Page, number: str) -> None:
        filled = await self._fill_labeled_input(
            page,
            "Air Waybill Number",
            number,
            css_fallback=(
                'input[name*="waybill" i], input[id*="waybill" i], '
                'input[name*="awb" i], input[id*="awb" i], '
                'input[name*="number" i], input[id*="number" i]'
            ),
            required=False,
        )
        if filled:
            return

        normalized = normalize_waybill_number(number)
        if len(normalized) > 3:
            parts = [normalized[:3], normalized[3:]]
            if await self._fill_split_inputs_near_label(
                page,
                self._label_pattern("Air Waybill Number"),
                "Air Waybill Number",
                parts,
            ):
                return

        await self._raise_page_error_if_present(page)
        raise AllineWaybillUploadError("Air Waybill Number field not found")

    def _label_pattern(self, label: str) -> re.Pattern:
        words = [re.escape(word) for word in label.strip().split()]
        return re.compile(r"\s+".join(words), re.I)

    async def _try_fill_locator(
        self,
        locator: Locator,
        label: str,
        value: str,
    ) -> bool:
        try:
            count = await locator.count()
        except Exception:
            logger.debug("Failed to count %s locator", label, exc_info=True)
            return False

        for index in range(min(count, 12)):
            candidate = locator.nth(index)
            try:
                if not await candidate.is_visible() or not await candidate.is_enabled():
                    continue
                await candidate.fill(value)
                return True
            except Exception:
                logger.debug("Failed to fill %s candidate", label, exc_info=True)
        return False

    async def _fill_input_near_label(
        self,
        page: Page,
        label_pattern: re.Pattern,
        label: str,
        value: str,
    ) -> bool:
        for inputs in await self._find_inputs_near_label(page, label_pattern):
            if await self._try_fill_locator(inputs, label, value):
                return True
        return False

    async def _fill_split_inputs_near_label(
        self,
        page: Page,
        label_pattern: re.Pattern,
        label: str,
        values: list[str],
    ) -> bool:
        for inputs in await self._find_inputs_near_label(page, label_pattern):
            try:
                count = await inputs.count()
            except Exception:
                logger.debug("Failed to count split %s inputs", label, exc_info=True)
                continue
            if count < len(values):
                continue

            filled_inputs = 0
            for index, value in enumerate(values):
                candidate = inputs.nth(index)
                try:
                    if not await candidate.is_visible() or not await candidate.is_enabled():
                        break
                    await candidate.fill(value)
                    filled_inputs += 1
                except Exception:
                    logger.debug("Failed to fill split %s input", label, exc_info=True)
                    break
            if filled_inputs == len(values):
                return True
        return False

    async def _find_inputs_near_label(
        self,
        page: Page,
        label_pattern: re.Pattern,
    ) -> list[Locator]:
        label_nodes = page.get_by_text(label_pattern)
        input_selector = 'input:not([type="hidden"]):not([type="file"]), textarea'
        locators: list[Locator] = []
        try:
            count = await label_nodes.count()
        except Exception:
            logger.debug("Failed to count label nodes", exc_info=True)
            return locators

        for index in range(min(count, 8)):
            label_node = label_nodes.nth(index)
            label = label_node.locator("xpath=ancestor-or-self::label[1]")
            if await label.count():
                locators.append(
                    label.locator(
                        "xpath=following-sibling::*[1]//input[not(@type='hidden') and not(@type='file')]"
                    )
                )
                locators.append(
                    label.locator("xpath=following-sibling::*[1]//textarea")
                )
                locators.append(label.locator(input_selector))

            containers = [
                label_node.locator("xpath=ancestor::label[1]"),
                label_node.locator("xpath=ancestor::div[1]"),
                label_node.locator("xpath=ancestor::fieldset[1]"),
            ]
            for container in containers:
                if await container.count():
                    locators.append(container.locator(input_selector))
            locators.append(
                label_node.locator(
                    "xpath=following::input[not(@type='hidden') and not(@type='file')][1]"
                )
            )
        return locators

    async def _set_file_input(
        self,
        page: Page,
        paths: list[str],
        *,
        preferred_label: str,
        fallback_position: str,
    ) -> None:
        label_input = page.get_by_label(re.compile(preferred_label, re.I)).first
        if await label_input.count():
            try:
                await label_input.set_input_files(paths)
                return
            except Exception:
                logger.debug("Failed to set %s labeled file input", preferred_label, exc_info=True)

        file_inputs = page.locator('input[type="file"]')
        count = await file_inputs.count()
        if not count:
            raise AllineWaybillUploadError(f"{preferred_label} file input not found")
        index = 0 if fallback_position == "first" else count - 1
        await file_inputs.nth(index).set_input_files(paths)

    async def _upload_pre_alert_dropzone(self, page: Page, pre_alert_path: str) -> None:
        step = page.locator("#step-2").first
        dropzone = step.locator("#dropzone").first
        await dropzone.wait_for(state="visible")

        file_inputs = page.locator(
            '#step-2 input[type="file"], input.dz-hidden-input[type="file"]'
        )
        count = await file_inputs.count()
        if count:
            await file_inputs.nth(count - 1).set_input_files(pre_alert_path)
            return

        try:
            async with page.expect_file_chooser(
                timeout=min(self.settings.playwright_timeout_ms, 8_000)
            ) as file_chooser_info:
                await dropzone.click()
            file_chooser = await file_chooser_info.value
            await file_chooser.set_files(pre_alert_path)
        except PlaywrightTimeoutError as exc:
            raise AllineWaybillUploadError(
                "Customer Pre Alert dropzone file input not found"
            ) from exc

    async def _wait_for_dropzone_upload(self, page: Page) -> None:
        timeout_ms = self._pre_alert_upload_timeout_ms()
        dropzone = page.locator("#step-2 #dropzone").first
        await dropzone.locator(".dz-preview").first.wait_for(
            state="attached",
            timeout=timeout_ms,
        )
        try:
            await page.wait_for_load_state("networkidle", timeout=min(timeout_ms, 30_000))
        except PlaywrightTimeoutError:
            logger.debug("ALLINE networkidle was not reached after Pre Alert file selection")

        try:
            await page.wait_for_function(
                """
                () => {
                  const dropzone = document.querySelector("#step-2 #dropzone");
                  if (!dropzone) return false;
                  const previews = Array.from(dropzone.querySelectorAll(".dz-preview"));
                  const hasPreview = previews.length > 0;
                  const hasError = Boolean(dropzone.querySelector(".dz-error"));
                  const hasSuccessClass = Boolean(
                    dropzone.querySelector(".dz-success, .dz-complete")
                  );
                  const dropzoneApi = dropzone.dropzone;
                  const apiFiles = Array.isArray(dropzoneApi?.files)
                    ? dropzoneApi.files
                    : [];
                  const apiFinished = apiFiles.length > 0 &&
                    apiFiles.every((file) => ["success", "canceled"].includes(file.status));
                  return hasPreview && !hasError && (hasSuccessClass || apiFinished);
                }
                """,
                timeout=timeout_ms,
            )
        except PlaywrightTimeoutError as exc:
            state = await self._get_dropzone_state(page)
            raise AllineWaybillUploadError(
                "Customer Pre Alert upload did not finish in ALLINE"
                + (f" ({state})" if state else "")
            ) from exc

        state = await self._get_dropzone_state(page)
        logger.info("ALLINE Customer Pre Alert upload finished: %s", state or "ready")
        error_texts = []
        errors = dropzone.locator(".dz-error-message")
        for index in range(min(await errors.count(), 5)):
            error = errors.nth(index)
            try:
                if await error.is_visible():
                    text = (await error.inner_text()).strip()
                    if text:
                        error_texts.append(text)
            except Exception:
                logger.debug("Failed to read dropzone error", exc_info=True)
        if error_texts:
            raise AllineWaybillUploadError("; ".join(error_texts))

    def _pre_alert_upload_timeout_ms(self) -> int:
        return max(
            self.settings.playwright_timeout_ms,
            self.settings.alline_pre_alert_upload_timeout_ms,
        )

    async def _get_dropzone_state(self, page: Page) -> str:
        try:
            state = await page.locator("#step-2 #dropzone").first.evaluate(
                """
                (dropzone) => {
                  const previews = Array.from(dropzone.querySelectorAll(".dz-preview"));
                  return previews.map((preview) => {
                    const name = preview.querySelector("[data-dz-name]")?.textContent?.trim();
                    const progress = preview.querySelector("[data-dz-uploadprogress]")
                      ?.style?.width;
                    const error = preview.querySelector("[data-dz-errormessage]")
                      ?.textContent?.trim();
                    const apiFile = dropzone.dropzone?.files?.find((file) => file.name === name);
                    return {
                      name,
                      classes: preview.className,
                      progress,
                      status: apiFile?.status,
                      error,
                    };
                  });
                }
                """
            )
        except Exception:
            logger.debug("Failed to read ALLINE dropzone state", exc_info=True)
            return ""
        if not state:
            return "no Dropzone preview found"
        parts = []
        for item in state[:3]:
            summary = ", ".join(
                str(value)
                for value in [
                    item.get("name"),
                    item.get("status"),
                    item.get("classes"),
                    item.get("progress"),
                    item.get("error"),
                ]
                if value
            )
            if summary:
                parts.append(summary)
        return "; ".join(parts)

    async def _click_button(self, page: Page, patterns: list[str], label: str) -> None:
        for pattern in patterns:
            locator = page.get_by_role("button", name=re.compile(pattern, re.I))
            buttons = await locator.all()
            for button in buttons:
                try:
                    if await button.is_enabled():
                        await button.click()
                        await page.wait_for_load_state("networkidle")
                        await self._raise_page_error_if_present(page)
                        return
                except AllineWaybillUploadError:
                    raise
                except Exception:
                    logger.debug("Failed to click %s candidate", label, exc_info=True)
        await self._raise_page_error_if_present(page)
        raise AllineWaybillUploadError(f"{label} not found or disabled")

    async def _wait_for_step_visible(
        self,
        page: Page,
        step_id: str,
        current_step_label: str,
    ) -> None:
        try:
            await page.locator(f"#{step_id}").wait_for(
                state="visible",
                timeout=min(self.settings.playwright_timeout_ms, 8_000),
            )
        except PlaywrightTimeoutError as exc:
            await self._raise_page_error_if_present(page)
            raise AllineWaybillUploadError(
                f"{current_step_label} did not advance to the next step"
            ) from exc

    async def _raise_page_error_if_present(self, page: Page) -> None:
        error_selectors = [
            ".invalid-feedback",
            ".alert-danger",
            ".ui-alert--danger",
            ".v-messages__message",
            "[class*='error-message']",
        ]
        error_lines: list[str] = []
        for selector in error_selectors:
            locator = page.locator(selector)
            try:
                count = await locator.count()
            except Exception:
                continue
            for index in range(min(count, 20)):
                item = locator.nth(index)
                try:
                    if await item.is_visible():
                        text = (await item.inner_text()).strip()
                        if text:
                            error_lines.append(text)
                except Exception:
                    logger.debug("Failed to read error candidate", exc_info=True)

        if error_lines:
            raise AllineWaybillUploadError("; ".join(dict.fromkeys(error_lines[:8])))
        return
        body_text = await page.locator("body").inner_text()
        error_lines = [
            line.strip()
            for line in body_text.splitlines()
            if re.search(r"error|failed|required|invalid|already|失败|错误|必填", line, re.I)
        ]
        if error_lines:
            raise AllineWaybillUploadError("; ".join(error_lines[:5]))

    async def _save_failure_artifacts(
        self,
        page: Page,
        upload: WaybillUpload,
    ) -> None:
        try:
            upload_files = list(upload.files)
            if upload_files:
                output_dir = Path(upload_files[0].storage_path).parent
            else:
                output_dir = Path(self.settings.upload_storage_dir) / str(upload.id)
                if not output_dir.is_absolute():
                    output_dir = Path.cwd() / output_dir
            output_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
            html_path = output_dir / f"alline_failure_{stamp}.html"
            screenshot_path = output_dir / f"alline_failure_{stamp}.png"
            html_path.write_text(await page.content(), encoding="utf-8")
            await page.screenshot(path=str(screenshot_path), full_page=True)
            logger.info(
                "Saved ALLINE failure artifacts for %s: %s, %s",
                upload.air_waybill_number,
                html_path,
                screenshot_path,
            )
        except Exception:
            logger.debug("Failed to save ALLINE failure artifacts", exc_info=True)
