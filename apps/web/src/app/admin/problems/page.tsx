import { redirect } from "next/navigation";
import { adminFetch, isAdmin, type ProblemItem } from "@/lib/admin";

export const dynamic = "force-dynamic";

/** Dead-lettered records: parse failures and quality-gate rejections, read-only. */
export default async function ProblemsPage() {
  if (!(await isAdmin())) redirect("/admin/login");
  const items = await adminFetch<ProblemItem[]>("/api/v1/admin/problems");

  return (
    <div className="space-y-4">
      <div className="flex items-baseline justify-between">
        <h1 className="text-2xl font-semibold">문제 레코드</h1>
        <span className="text-sm text-muted">{items.length}건</span>
      </div>
      {items.length === 0 ? (
        <p className="text-muted">파싱 실패나 품질 게이트 거절이 없습니다.</p>
      ) : (
        <ul className="divide-y divide-line rounded-lg border border-line bg-card">
          {items.map((p) => (
            <li key={p.stagingId} className="p-3 text-sm">
              <div className="flex flex-wrap items-baseline gap-x-3">
                <span className="rounded bg-accent-soft px-2 py-0.5 text-xs text-accent">{p.status}</span>
                <span className="font-medium">{p.dramaTitle ?? "(제목 없음)"}</span>
                <span className="text-muted">
                  {p.sourceCode} · staging #{p.stagingId} · {p.updatedAt.slice(0, 16).replace("T", " ")}
                </span>
              </div>
              <ul className="mt-1 space-y-0.5 text-xs text-muted">
                {p.issues.map((i, n) => (
                  <li key={n}>
                    <span className={i.severity === "ERROR" ? "text-accent" : ""}>{i.code}</span> — {i.message}
                  </li>
                ))}
              </ul>
            </li>
          ))}
        </ul>
      )}
      <p className="text-xs text-muted">
        파싱 실패는 파서 버전을 올리면 자동 재시도되고, 거절 건은 seed/source 데이터를 고쳐 재수집합니다.
      </p>
    </div>
  );
}
