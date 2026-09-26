import { apiClient } from "@/lib/api-client";
import type { UploadResponse } from "@/types";

export const MAX_UPLOAD_SIZE = 20 * 1024 * 1024;
export const ACCEPTED_FILE_TYPES = ["application/pdf", "image/png", "image/jpeg", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"];

export async function uploadDocument(
  file: File,
  documentType: string,
  title?: string,
  onProgress?: (progress: number) => void,
): Promise<UploadResponse> {
  const form = new FormData();
  form.append("file", file);
  form.append("document_type", documentType);
  if (title?.trim()) form.append("title", title.trim());
  return apiClient.upload<UploadResponse>("/upload", form, onProgress);
}
