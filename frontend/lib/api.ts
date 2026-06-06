import type {
  AppUser,
  AuthUserResponse,
  UserCreateRequest,
  UserListResponse,
  WaybillFilters,
  WaybillItem,
  WaybillListResponse,
  WaybillUploadItem,
  WaybillUploadDeleteResponse,
  WaybillUploadFilters,
  WaybillPreAlertUploadPayload,
  WaybillPreAlertUploadResponse,
  WaybillUploadListResponse,
  WaybillUploadStatus,
  WaybillUpdatePayload
} from "./types";

const REQUEST_TIMEOUT_MS = 12_000;
const AUTH_REQUEST_TIMEOUT_MS = 5_000;
const UPLOAD_REQUEST_TIMEOUT_MS = 60_000;

type JsonRequestInit = RequestInit & {
  timeoutMs?: number;
  timeoutMessage?: string;
};

function parseErrorDetail(rawDetail: string) {
  if (!rawDetail) {
    return "";
  }

  try {
    const parsed = JSON.parse(rawDetail) as { detail?: unknown };
    if (typeof parsed.detail === "string") {
      return parsed.detail;
    }
    if (Array.isArray(parsed.detail)) {
      return parsed.detail
        .map((item) => {
          if (typeof item === "string") {
            return item;
          }
          if (item && typeof item === "object" && "msg" in item) {
            return String((item as { msg: unknown }).msg);
          }
          return JSON.stringify(item);
        })
        .join("; ");
    }
  } catch {
    return rawDetail;
  }

  return rawDetail;
}

function getApiBaseUrl() {
  const configured =
    process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ??
    "http://127.0.0.1:8000";

  if (typeof window === "undefined") {
    return configured;
  }

  if (
    configured.includes("://localhost:") ||
    configured.includes("://127.0.0.1:")
  ) {
    return "";
  }

  const pageHost = window.location.hostname;
  if (pageHost === "127.0.0.1" && configured.includes("://localhost:")) {
    return configured.replace("://localhost:", "://127.0.0.1:");
  }
  if (pageHost === "localhost" && configured.includes("://127.0.0.1:")) {
    return configured.replace("://127.0.0.1:", "://localhost:");
  }

  return configured;
}

function getRequestUrl(path: string) {
  const baseUrl = getApiBaseUrl();
  if (!baseUrl) {
    return path.replace(/^\/api\/v1/, "/backend/v1");
  }
  return `${baseUrl}${path}`;
}

async function requestJson<T>(path: string, init?: JsonRequestInit): Promise<T> {
  const {
    timeoutMs = REQUEST_TIMEOUT_MS,
    timeoutMessage = "Request timed out. Please check whether the backend is running.",
    ...fetchInit
  } = init ?? {};
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  const isFormData =
    typeof FormData !== "undefined" && fetchInit.body instanceof FormData;
  const headers = isFormData
    ? fetchInit.headers
    : {
        "Content-Type": "application/json",
        ...(fetchInit.headers ?? {})
      };

  let response: Response;
  try {
    response = await fetch(getRequestUrl(path), {
      ...fetchInit,
      credentials: "include",
      signal: controller.signal,
      headers
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new Error(timeoutMessage);
    }
    throw error;
  } finally {
    clearTimeout(timeout);
  }

  if (!response.ok) {
    const detail = await response.text();
    const parsedDetail = parseErrorDetail(detail);
    throw new Error(
      `Request failed with ${response.status}${parsedDetail ? `: ${parsedDetail}` : ""}`
    );
  }

  return response.json() as Promise<T>;
}

export function login(email: string, password: string): Promise<AuthUserResponse> {
  return requestJson<AuthUserResponse>("/api/v1/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password })
  });
}

export function logout(): Promise<{ status: string }> {
  return requestJson<{ status: string }>("/api/v1/auth/logout", {
    method: "POST"
  });
}

export function getCurrentUser(): Promise<AuthUserResponse> {
  return requestJson<AuthUserResponse>("/api/v1/auth/me", {
    timeoutMs: AUTH_REQUEST_TIMEOUT_MS,
    timeoutMessage:
      "Account information request timed out. Please check whether the backend is running."
  });
}

export function listUsers(): Promise<UserListResponse> {
  return requestJson<UserListResponse>("/api/v1/users");
}

export function createUser(payload: UserCreateRequest): Promise<AppUser> {
  return requestJson<AppUser>("/api/v1/users", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function updateUserStatus(
  userId: string,
  status: "active" | "disabled"
): Promise<AppUser> {
  return requestJson<AppUser>(`/api/v1/users/${userId}`, {
    method: "PATCH",
    body: JSON.stringify({ status })
  });
}

export function resetUserPassword(
  userId: string,
  password: string
): Promise<AppUser> {
  return requestJson<AppUser>(`/api/v1/users/${userId}/reset-password`, {
    method: "POST",
    body: JSON.stringify({ password })
  });
}

export function listWaybillUploads(
  filters?: WaybillUploadFilters
): Promise<WaybillUploadListResponse> {
  const params = new URLSearchParams();
  if (filters?.userId) {
    params.set("userId", filters.userId);
  }
  if (filters?.status) {
    params.set("status", filters.status);
  }
  if (filters?.q?.trim()) {
    params.set("q", filters.q.trim());
  }

  const query = params.toString();
  return requestJson<WaybillUploadListResponse>(
    `/api/v1/waybill-uploads${query ? `?${query}` : ""}`
  );
}

export function uploadPreAlertFile(
  payload: WaybillPreAlertUploadPayload
): Promise<WaybillPreAlertUploadResponse> {
  const formData = new FormData();
  formData.append("shipmentType", payload.shipmentType);
  formData.append("airWaybillNumber", payload.airWaybillNumber);
  formData.append("grossWeightKg", payload.grossWeightKg);
  formData.append("pieces", payload.pieces);
  if (payload.arrivalFlightNumber) {
    formData.append("arrivalFlightNumber", payload.arrivalFlightNumber);
  }
  if (payload.targetUserId) {
    formData.append("targetUserId", payload.targetUserId);
  }
  for (const file of payload.airWaybillDocuments) {
    formData.append("airWaybillDocuments", file);
  }
  formData.append("preAlertFile", payload.preAlertFile);

  return requestJson<WaybillPreAlertUploadResponse>("/api/v1/waybill-uploads/file", {
    method: "POST",
    body: formData,
    timeoutMs: UPLOAD_REQUEST_TIMEOUT_MS,
    timeoutMessage:
      "Upload is taking longer than expected. Please keep the backend running and check the upload list."
  });
}

export function updateWaybillUploadStatus(
  uploadId: string,
  status: WaybillUploadStatus
): Promise<WaybillUploadItem> {
  return requestJson<WaybillUploadItem>(
    `/api/v1/waybill-uploads/${uploadId}/status`,
    {
      method: "PATCH",
      body: JSON.stringify({ status })
    }
  );
}

export function deleteWaybillUpload(
  uploadId: string
): Promise<WaybillUploadDeleteResponse> {
  return requestJson<WaybillUploadDeleteResponse>(
    `/api/v1/waybill-uploads/${uploadId}`,
    {
      method: "DELETE"
    }
  );
}

export function getWaybillUploadFileDownloadUrl(
  uploadId: string,
  fileId: string
) {
  return getRequestUrl(
    `/api/v1/waybill-uploads/${uploadId}/files/${fileId}/download`
  );
}

export function listWaybills(filters?: WaybillFilters): Promise<WaybillListResponse> {
  const params = new URLSearchParams();
  if (filters?.userId) {
    params.set("userId", filters.userId);
  }
  if (filters?.status) {
    params.set("status", filters.status);
  }
  if (filters?.q?.trim()) {
    params.set("q", filters.q.trim());
  }

  const query = params.toString();
  return requestJson<WaybillListResponse>(
    `/api/v1/waybills${query ? `?${query}` : ""}`
  );
}

export function getWaybill(publicCode: string): Promise<WaybillItem> {
  return requestJson<WaybillItem>(`/api/v1/waybills/${publicCode}`);
}

export function updateWaybill(
  publicCode: string,
  payload: WaybillUpdatePayload
): Promise<WaybillItem> {
  return requestJson<WaybillItem>(`/api/v1/waybills/${publicCode}`, {
    method: "PATCH",
    body: JSON.stringify(payload)
  });
}

export function isUnauthorizedError(error: unknown): boolean {
  return error instanceof Error && error.message.includes("401");
}
