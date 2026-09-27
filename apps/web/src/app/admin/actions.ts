"use server";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { revalidatePath } from "next/cache";
import { ADMIN_COOKIE, adminFetch, isAdmin, tokenMatches } from "@/lib/admin";

export async function login(formData: FormData): Promise<void> {
  const token = String(formData.get("token") ?? "");
  if (!tokenMatches(token)) {
    redirect("/admin/login?error=1");
  }
  const jar = await cookies();
  jar.set(ADMIN_COOKIE, token, {
    httpOnly: true,
    sameSite: "strict",
    secure: process.env.SESSION_COOKIE_SECURE === "true",
    path: "/admin",
    maxAge: 60 * 60 * 8,
  });
  redirect("/admin/review");
}

export async function logout(): Promise<void> {
  const jar = await cookies();
  jar.delete({ name: ADMIN_COOKIE, path: "/admin" });
  redirect("/admin/login");
}

/** One decision per click: merge into the candidate, or create a new canonical entity. */
export async function decide(formData: FormData): Promise<void> {
  if (!(await isAdmin())) redirect("/admin/login");
  const stagingId = Number(formData.get("stagingId"));
  const decision = String(formData.get("decision"));
  const canonicalId = formData.get("canonicalId");
  await adminFetch(`/api/v1/admin/review/${stagingId}/decide`, {
    method: "POST",
    body: JSON.stringify({
      decisions: [
        {
          kind: String(formData.get("kind")),
          key: String(formData.get("key")),
          decision,
          canonicalId: decision === "AUTO_MERGE" && canonicalId ? Number(canonicalId) : null,
        },
      ],
    }),
  });
  revalidatePath("/admin/review");
}
