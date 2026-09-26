import { apiClient } from "@/lib/api-client";
import type { RightArticle } from "@/types";

export async function listRights(): Promise<RightArticle[]> {
  return apiClient.get<RightArticle[]>("/rights");
}
