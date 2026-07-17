export type UserRole = "admin" | "user";
export type UserStatus = "active" | "disabled";

export interface AppUser {
  id: string;
  email: string;
  username: string;
  role: UserRole;
  status: UserStatus;
  balance: string;
  lastLoginAt?: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface AuthUserResponse {
  user: AppUser;
}

export interface UserListResponse {
  items: AppUser[];
}

export interface UserCreateRequest {
  email: string;
  username: string;
  password: string;
}

export interface BillingReceiptItem {
  originalFilename: string;
  contentType?: string | null;
  sizeBytes: number;
}

export interface BillingEntryItem {
  id: string;
  entryType: "recharge" | "deduction";
  amount: string;
  currency: string;
  balanceAfter: string;
  waybillUploadId?: string | null;
  waybillNumber?: string | null;
  supplierId?: string | null;
  supplierName?: string | null;
  supplierVersionNumber?: number | null;
  arrivalAirport?: string | null;
  billableUnitCount?: number | null;
  unitRate?: string | null;
  billingSource?: "upload" | "retroactive" | null;
  createdByUserId?: string | null;
  receipt?: BillingReceiptItem | null;
  createdAt: string;
}

export interface BillingAccountResponse {
  user: AppUser;
  deductions: BillingEntryItem[];
  recharges: BillingEntryItem[];
}

export interface BillingTaxEstimateResponse {
  supplierId: string;
  supplierName: string;
  supplierVersionId: string;
  supplierVersionNumber: number;
  taxableAirport: boolean;
  billableUnitCount: number;
  unitRate: string;
  estimatedTax: string;
  warningCount: number;
  warnings: SupplierValidationIssue[];
  currency: "EUR";
}

export type SupplierSemanticField =
  | "parcel_unit_number"
  | "destination"
  | "number_of_items"
  | "weight_kg";

export interface SupplierRuleConstraints {
  minValue?: string | null;
  maxValue?: string | null;
  minLength?: number | null;
  maxLength?: number | null;
  pattern?: string | null;
  allowedValues: string[];
  unique: boolean;
}

export interface SupplierFieldRule {
  key: string;
  name: string;
  semanticField?: SupplierSemanticField | null;
  locatorMode: "column" | "header";
  locatorValue: string;
  valueType: "text" | "number" | "integer" | "country";
  blankPolicy: "allow" | "required" | "skip_row";
  caseInsensitive: boolean;
  allowUnknownCountry: boolean;
  countryAliases: Record<string, string>;
  constraints: SupplierRuleConstraints;
}

export interface SupplierVersionConfig {
  workbook: {
    sheetMode: "first" | "named";
    sheetName?: string | null;
    headerRow: number;
    dataStartRow: number;
  };
  fields: SupplierFieldRule[];
  rowKeyFieldKey: string;
  billingGroupFieldKey: string;
  billingDistinctFieldKey: string;
}

export interface SupplierVersionItem {
  id: string;
  versionNumber: number;
  config: SupplierVersionConfig;
  createdByUserId?: string | null;
  createdAt: string;
}

export interface SupplierItem {
  id: string;
  name: string;
  status: "active" | "inactive";
  currentVersionNumber: number;
  currentVersion: SupplierVersionItem;
  createdAt: string;
  updatedAt: string;
}

export interface SupplierListResponse {
  items: SupplierItem[];
}

export interface BillingSettingsItem {
  unitTaxEur: string;
  taxableAirports: string[];
  taxEffectiveDate: string;
  updatedAt: string;
}

export interface RetroactiveBillingSuccessItem {
  waybillNumber: string;
  supplierName: string;
  supplierVersionNumber: number;
  billableUnitCount: number;
  unitRate: string;
  amount: string;
  balanceAfter: string;
  warningCount: number;
}

export interface RetroactiveBillingFailureItem {
  waybillNumber: string;
  reason: string;
}

export interface RetroactiveBillingResponse {
  requestedCount: number;
  succeededCount: number;
  failedCount: number;
  succeeded: RetroactiveBillingSuccessItem[];
  failed: RetroactiveBillingFailureItem[];
}

export interface SupplierValidationIssue {
  ruleKey: string;
  ruleName: string;
  rowNumber: number;
  column: string;
  message: string;
  rawValue: string;
}

export type ShipmentType = "Air" | "Road" | "Train";
export type WaybillUploadStatus = "pending_review" | "approved" | "rejected";
export type WaybillTrackingStatus =
  | "created"
  | "noa_received"
  | "received"
  | "ready_to_scan"
  | "scanning"
  | "pending_clearance"
  | "cleared"
  | "partial_inbound"
  | "inbound"
  | "partial_outbound"
  | "outbound";
export type WaybillFycoStatus = "released" | "fyco";
export type WaybillParcelStatus =
  | "created"
  | "pending_check"
  | "inspection"
  | "released"
  | "temporary_released"
  | "exception"
  | "confiscated"
  | "destroyed"
  | "on_hold"
  | "inbound"
  | "outbound";

export interface WaybillPreAlertUploadPayload {
  shipmentType: ShipmentType;
  airWaybillNumber: string;
  grossWeightKg: string;
  pieces: string;
  arrivalFlightNumber?: string;
  airportOfDeparture: string;
  airportOfArrival: string;
  targetUserId?: string;
  supplierId: string;
  airWaybillDocuments: File[];
  preAlertFile: File;
}

export interface WaybillPreAlertUploadResponse {
  uploadId: string;
  airWaybillNumber: string;
  airportOfDeparture: string;
  airportOfArrival: string;
  status: WaybillUploadStatus;
  boundUserId: string;
  supplierId: string;
  supplierName: string;
  supplierVersionNumber: number;
  billableUnitCount: number;
  unitRate: string;
  deductedTax: string;
  balanceAfter: string;
  validationIssueCount: number;
  validationIssues: SupplierValidationIssue[];
}

export interface WaybillUploadFileItem {
  id: string;
  fileKind: "air_waybill_document" | "customer_pre_alert" | string;
  originalFilename: string;
  contentType?: string | null;
  sizeBytes: number;
  sha256: string;
  createdAt: string;
}

export interface WaybillUploadUserItem {
  id: string;
  email: string;
  username: string;
}

export interface WaybillUploadItem {
  id: string;
  userId: string;
  uploadedByUserId?: string | null;
  supplierId: string;
  supplierVersionId: string;
  supplierName?: string | null;
  supplierVersionNumber?: number | null;
  shipmentType: ShipmentType;
  airWaybillNumber: string;
  grossWeightKg: string;
  pieces: number;
  arrivalFlightNumber?: string | null;
  airportOfDeparture?: string | null;
  airportOfArrival?: string | null;
  status: WaybillUploadStatus;
  validationIssueCount: number;
  validationIssues: SupplierValidationIssue[];
  reviewedByUserId?: string | null;
  reviewedAt?: string | null;
  createdAt: string;
  updatedAt: string;
  user?: WaybillUploadUserItem | null;
  uploadedBy?: WaybillUploadUserItem | null;
  files: WaybillUploadFileItem[];
}

export interface WaybillUploadListResponse {
  items: WaybillUploadItem[];
}

export interface WaybillUploadFilters {
  userId?: string;
  status?: WaybillUploadStatus | "";
  q?: string;
}

export interface WaybillUploadDeleteResponse {
  status: "deleted";
  uploadId: string;
}

export interface WaybillPodFileItem {
  id: string;
  originalFilename: string;
  contentType?: string | null;
  sizeBytes: number;
  createdAt: string;
}

export interface WaybillPodDeleteResponse {
  status: "deleted";
  podFileId: string;
}

export interface WaybillParcelItem {
  id: string;
  parcelUnitNumber: string;
  status: WaybillParcelStatus;
  numberOfItems?: number | null;
  weightKg?: string | null;
  destinationRaw?: string | null;
  destinationCode?: string | null;
  destinationName?: string | null;
  inbound: boolean;
  outbound: boolean;
  specialInstruction: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface WaybillParcelListResponse {
  items: WaybillParcelItem[];
}

export interface WaybillParcelBulkUpdatePayload {
  parcelIds: string[];
  status?: WaybillParcelStatus;
  inbound?: boolean;
  outbound?: boolean;
  specialInstruction?: boolean;
}

export interface WaybillItem {
  id: string;
  publicCode: string;
  uploadId: string;
  userId: string;
  number: string;
  status: WaybillTrackingStatus;
  airportOfDeparture?: string | null;
  airportOfArrival?: string | null;
  statusChangedAt: string;
  weightKg: string;
  pieces: number;
  customsCartons?: number | null;
  customsAmount?: string | null;
  receivedCount: number;
  receivedTotal: number;
  inWarehouseCount: number;
  palletCount: number;
  fycoStatus?: WaybillFycoStatus | null;
  releasedCount: number;
  outboundCount: number;
  noaAt?: string | null;
  collectionAt?: string | null;
  scannedAt?: string | null;
  customsClearanceAt?: string | null;
  outboundAt?: string | null;
  createdAt: string;
  updatedAt: string;
  user?: WaybillUploadUserItem | null;
  podFiles: WaybillPodFileItem[];
}

export interface WaybillListResponse {
  items: WaybillItem[];
}

export interface WaybillFilters {
  userId?: string;
  status?: WaybillTrackingStatus | "";
  q?: string;
}

export interface WaybillUpdatePayload {
  status?: WaybillTrackingStatus;
  airportOfDeparture?: string;
  airportOfArrival?: string;
  receivedCount?: number;
  receivedTotal?: number;
  inWarehouseCount?: number;
  palletCount?: number;
  fycoStatus?: WaybillFycoStatus | null;
  releasedCount?: number;
  outboundCount?: number;
  noaAt?: string | null;
  collectionAt?: string | null;
  scannedAt?: string | null;
  customsClearanceAt?: string | null;
  outboundAt?: string | null;
}
