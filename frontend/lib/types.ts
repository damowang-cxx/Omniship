export type UserRole = "admin" | "user";
export type UserStatus = "active" | "disabled";

export interface AppUser {
  id: string;
  email: string;
  username: string;
  role: UserRole;
  status: UserStatus;
  balance: string;
  payerCompanyName?: string | null;
  payerAddressInfo?: string | null;
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
  entryType: "recharge" | "recharge_reversal" | "deduction" | "deduction_reversal";
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
  billingSource?: "upload" | "retroactive" | "cancellation" | null;
  reversalOfEntryId?: string | null;
  reversedByEntryId?: string | null;
  createdByUserId?: string | null;
  receipt?: BillingReceiptItem | null;
  createdAt: string;
}

export interface BillingAccountResponse {
  user: AppUser;
  deductions: BillingEntryItem[];
  recharges: BillingEntryItem[];
}

export interface InvoiceSettingsItem {
  issuerCompanyName?: string | null;
  issuerAddressInfo?: string | null;
  beneficiaryName?: string | null;
  bankAccount?: string | null;
  bankNameAndCode?: string | null;
  branchCode?: string | null;
  swiftBic?: string | null;
  bankAddress?: string | null;
  stampOriginalFilename?: string | null;
  updatedAt?: string | null;
}

export interface InvoiceEligibleDeductionItem {
  id: string;
  waybillNumber: string;
  quantity: number;
  unitRate: string;
  amount: string;
  extraFeeTotal: string;
  totalAmount: string;
  recordedAt: string;
}

export interface InvoiceLineItem {
  id: string;
  billingEntryId: string;
  lineNumber: number;
  waybillNumber: string;
  quantity: number;
  unitRate: string;
  amount: string;
  extraFeeTotal: string;
  totalAmount: string;
}

export interface InvoiceItem {
  id: string;
  invoiceNumber: string;
  status: "issued" | "voided";
  issuedDate: string;
  dueDate: string;
  totalAmount: string;
  payer: { companyName: string; addressInfo: string };
  lines: InvoiceLineItem[];
  createdAt: string;
  voidedAt?: string | null;
  voidReason?: string | null;
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
  billingGroupColumn?: string | null;
  billingDistinctColumn?: string | null;
  /** Legacy references returned by supplier versions published before direct columns. */
  rowKeyFieldKey?: string | null;
  billingGroupFieldKey?: string | null;
  billingDistinctFieldKey?: string | null;
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

export interface CancelledWaybillItem {
  id: string;
  originalUploadId: string;
  userId?: string | null;
  userEmail: string;
  username: string;
  uploadedByEmail?: string | null;
  supplierId?: string | null;
  supplierName?: string | null;
  supplierVersionNumber?: number | null;
  shipmentType: ShipmentType;
  airWaybillNumber: string;
  grossWeightKg: string;
  pieces: number;
  arrivalFlightNumber?: string | null;
  airportOfDeparture?: string | null;
  airportOfArrival?: string | null;
  originalStatus: WaybillUploadStatus;
  uploadedAt: string;
  fileCount: number;
  taxAmountDeleted: string;
  refundedAmount: string;
  balanceAfterRefund?: string | null;
  currency: string;
  reason: string;
  cancelledByUserId?: string | null;
  cancelledByEmail: string;
  cancelledAt: string;
}

export interface CancelledWaybillListResponse {
  items: CancelledWaybillItem[];
}

export interface CancelWaybillResponse {
  status: "cancelled";
  uploadId: string;
  refundedAmount: string;
  balanceAfterRefund: string;
  record: CancelledWaybillItem;
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

export interface WaybillExtraFeeType {
  id: string;
  name: string;
  isActive: boolean;
}

export interface WaybillExtraFeeTypeDeleteResponse {
  status: "deactivated";
  feeTypeId: string;
}

export interface WaybillExtraFee {
  id: string;
  feeTypeId: string;
  feeTypeName: string;
  amount: string;
}

export interface WaybillExtraFeeUpdatePayload {
  items: Array<{ feeTypeId: string; amount: string }>;
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
  extraFees: WaybillExtraFee[];
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
