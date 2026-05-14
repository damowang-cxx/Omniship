from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.scrape_run import ScrapeRunSummary


class AirWaybillItem(BaseModel):
    number: str
    status: str | None = None
    weight_kg_raw: str | None = Field(default=None, alias="weightKgRaw")
    received_raw: str | None = Field(default=None, alias="receivedRaw")
    parcels_raw: str | None = Field(default=None, alias="parcelsRaw")
    in_warehouse_raw: str | None = Field(default=None, alias="inWarehouseRaw")
    released_raw: str | None = Field(default=None, alias="releasedRaw")
    outbound_raw: str | None = Field(default=None, alias="outboundRaw")
    actions_raw: str | None = Field(default=None, alias="actionsRaw")
    action_href: str | None = Field(default=None, alias="actionHref")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class AirWaybillLatestResponse(BaseModel):
    latest_run: ScrapeRunSummary | None = Field(default=None, alias="latestRun")
    items: list[AirWaybillItem]

    model_config = ConfigDict(populate_by_name=True)


class AirWaybillDetailItem(BaseModel):
    waybill_number: str = Field(alias="waybillNumber")
    waybill_status: str | None = Field(default=None, alias="waybillStatus")
    uploaded_on_raw: str | None = Field(default=None, alias="uploadedOnRaw")
    date_received_raw: str | None = Field(default=None, alias="dateReceivedRaw")
    airline_raw: str | None = Field(default=None, alias="airlineRaw")
    incoming_flight_raw: str | None = Field(default=None, alias="incomingFlightRaw")
    arrived_raw: str | None = Field(default=None, alias="arrivedRaw")
    ground_handler_raw: str | None = Field(default=None, alias="groundHandlerRaw")
    broker_raw: str | None = Field(default=None, alias="brokerRaw")
    units_raw: str | None = Field(default=None, alias="unitsRaw")
    units_inbound_raw: str | None = Field(default=None, alias="unitsInboundRaw")
    units_outbound_raw: str | None = Field(default=None, alias="unitsOutboundRaw")
    pre_alert_weight_raw: str | None = Field(default=None, alias="preAlertWeightRaw")
    gross_weight_raw: str | None = Field(default=None, alias="grossWeightRaw")
    odd_sized_raw: str | None = Field(default=None, alias="oddSizedRaw")
    scraped_at: datetime | None = Field(default=None, alias="scrapedAt")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class AirWaybillDestinationItem(BaseModel):
    name: str
    country: str | None = None
    units_received_raw: str | None = Field(default=None, alias="unitsReceivedRaw")
    units_outbound_raw: str | None = Field(default=None, alias="unitsOutboundRaw")
    total_weight_raw: str | None = Field(default=None, alias="totalWeightRaw")
    released_raw: str | None = Field(default=None, alias="releasedRaw")
    sort_order: int = Field(alias="sortOrder")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class AirWaybillDetailResponse(BaseModel):
    summary: AirWaybillItem
    detail: AirWaybillDetailItem | None = None
    destinations: list[AirWaybillDestinationItem]

    model_config = ConfigDict(populate_by_name=True)
