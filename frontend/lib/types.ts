export type ScrapeRunStatus = "running" | "success" | "failed";

export interface ScrapeRunSummary {
  runId: string;
  status: ScrapeRunStatus;
  mode?: "full" | "incremental" | string;
  rowCount: number;
  totalCount?: number;
  processedCount?: number;
  insertedCount?: number;
  updatedCount?: number;
  skippedCount?: number;
  detailFailedCount?: number;
  startedAt?: string | null;
  finishedAt?: string | null;
  errorMessage?: string | null;
}

export interface AirWaybillItem {
  number: string;
  status?: string | null;
  weightKgRaw?: string | null;
  receivedRaw?: string | null;
  parcelsRaw?: string | null;
  inWarehouseRaw?: string | null;
  releasedRaw?: string | null;
  outboundRaw?: string | null;
  actionsRaw?: string | null;
  actionHref?: string | null;
}

export interface AirWaybillLatestResponse {
  latestRun: ScrapeRunSummary | null;
  items: AirWaybillItem[];
}

export interface ScrapeStatusResponse {
  latestRun: ScrapeRunSummary | null;
}

export interface AirWaybillDetailItem {
  waybillNumber: string;
  waybillStatus?: string | null;
  uploadedOnRaw?: string | null;
  dateReceivedRaw?: string | null;
  airlineRaw?: string | null;
  incomingFlightRaw?: string | null;
  arrivedRaw?: string | null;
  groundHandlerRaw?: string | null;
  brokerRaw?: string | null;
  unitsRaw?: string | null;
  unitsInboundRaw?: string | null;
  unitsOutboundRaw?: string | null;
  preAlertWeightRaw?: string | null;
  grossWeightRaw?: string | null;
  oddSizedRaw?: string | null;
  scrapedAt?: string | null;
}

export interface AirWaybillDestinationItem {
  name: string;
  country?: string | null;
  unitsReceivedRaw?: string | null;
  unitsOutboundRaw?: string | null;
  totalWeightRaw?: string | null;
  releasedRaw?: string | null;
  sortOrder: number;
}

export interface AirWaybillDetailResponse {
  summary: AirWaybillItem;
  detail: AirWaybillDetailItem | null;
  destinations: AirWaybillDestinationItem[];
}

export type UserRole = "admin" | "user";
export type UserStatus = "active" | "disabled";

export interface AppUser {
  id: string;
  email: string;
  username: string;
  role: UserRole;
  status: UserStatus;
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

export interface WaybillUploadResponse {
  boundCount: number;
  skippedCount: number;
  numbers: string[];
}

export type ShipmentType = "Air" | "Road" | "Train";
export type UploadPlatform = "ALLINE";
export type PlatformSubmissionStatus = "pending" | "success" | "failed";
export type PlatformSubmissionMethod = "automated" | "manual";
export type WaybillUploadStatus = "pending_review" | "approved" | "rejected";

export interface WaybillPreAlertUploadPayload {
  platform: UploadPlatform;
  shipmentType: ShipmentType;
  airWaybillNumber: string;
  grossWeightKg: string;
  pieces: string;
  arrivalFlightNumber?: string;
  targetUserId?: string;
  airWaybillDocuments: File[];
  preAlertFile: File;
}

export interface WaybillPreAlertUploadResponse {
  uploadId: string;
  platform: UploadPlatform;
  airWaybillNumber: string;
  status: WaybillUploadStatus;
  platformSubmissionStatus: PlatformSubmissionStatus;
  platformSubmissionMethod: PlatformSubmissionMethod;
  platformSubmissionError?: string | null;
  platformSubmittedAt?: string | null;
  boundUserId: string;
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
  platform: UploadPlatform;
  shipmentType: ShipmentType;
  airWaybillNumber: string;
  grossWeightKg: string;
  pieces: number;
  arrivalFlightNumber?: string | null;
  status: WaybillUploadStatus;
  platformSubmissionStatus: PlatformSubmissionStatus;
  platformSubmissionMethod: PlatformSubmissionMethod;
  platformSubmissionError?: string | null;
  platformSubmittedAt?: string | null;
  reviewedByUserId?: string | null;
  reviewedAt?: string | null;
  createdAt: string;
  updatedAt: string;
  user?: WaybillUploadUserItem | null;
  files: WaybillUploadFileItem[];
}

export interface WaybillUploadListResponse {
  items: WaybillUploadItem[];
}

export interface WaybillUploadFilters {
  userId?: string;
  platformSubmissionStatus?: PlatformSubmissionStatus | "";
  status?: WaybillUploadStatus | "";
  q?: string;
}

export interface WaybillUploadDeleteResponse {
  status: "deleted";
  uploadId: string;
  removedBinding: boolean;
}
