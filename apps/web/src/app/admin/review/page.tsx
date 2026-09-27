import { redirect } from "next/navigation";
import { adminFetch, isAdmin, type ReviewEntity, type ReviewItem } from "@/lib/admin";
import { decide } from "../actions";

export const dynamic = "force-dynamic";

const KIND_LABEL: Record<ReviewEntity["kind"], string> = {
  persons: "인물",
  songs: "곡",
  artists: "아티스트",
  drama: "작품",
};

/**
 * Entity-resolution review queue (DM-104). Each undecided match shows the incoming
 * record next to the existing canonical candidate; the reviewer merges or creates.
 * Decisions are written to staging_record.resolution; publish_gold_catalog picks
 * them up on its next run (asset or 15-minute schedule).
 */
export default async function ReviewPage() {
  if (!(await isAdmin())) redirect("/admin/login");
  const items = await adminFetch<ReviewItem[]>("/api/v1/admin/review");

  return (
    <div className="space-y-6">
      <div className="flex items-baseline justify-between">
        <h1 className="text-2xl font-semibold">엔티티 리뷰 큐</h1>
        <span className="text-sm text-muted">{items.length}건</span>
      </div>
      {items.length === 0 ? (
        <p className="text-muted">검토할 항목이 없습니다.</p>
      ) : (
        <ul className="space-y-6">
          {items.map((item) => (
            <li key={item.stagingId} className="rounded-lg border border-line bg-card p-4">
              <div className="mb-3 flex flex-wrap items-baseline gap-x-3 text-sm">
                <span className="text-base font-semibold">{item.dramaTitle}</span>
                <span className="text-muted">
                  {item.sourceCode} · {item.dramaExternalId} · staging #{item.stagingId}
                </span>
              </div>
              <ul className="space-y-3">
                {item.entities.map((e) => (
                  <li key={`${e.kind}:${e.key}`} className="grid gap-3 rounded-md border border-line p-3 md:grid-cols-[1fr_1fr_auto]">
                    <div>
                      <div className="text-xs uppercase tracking-wide text-muted">들어온 {KIND_LABEL[e.kind]}</div>
                      <div className="font-medium">{e.incomingName}</div>
                      <div className="text-xs text-muted">
                        {[e.incomingContext, e.incomingBirthDate ? `${e.incomingBirthDate} 출생` : "생년월일 없음"]
                          .filter(Boolean)
                          .join(" · ")}
                      </div>
                      <div className="mt-1 text-xs text-muted">
                        신뢰도 {e.confidence?.toFixed(2) ?? "-"} ·{" "}
                        {Object.entries(e.signals)
                          .map(([k, v]) => `${k}=${v ?? "null"}`)
                          .join(", ")}
                      </div>
                    </div>
                    <div>
                      <div className="text-xs uppercase tracking-wide text-muted">기존 후보</div>
                      {e.candidate ? (
                        <>
                          <div className="font-medium">
                            {e.candidate.name}
                            {e.candidate.slug && <span className="ml-2 text-xs text-muted">/{e.candidate.slug}</span>}
                          </div>
                          <div className="text-xs text-muted">
                            {e.candidate.birthDate ? `${e.candidate.birthDate} 출생` : "생년월일 없음"}
                          </div>
                          {e.candidate.works.length > 0 && (
                            <div className="mt-1 text-xs text-muted">{e.candidate.works.join(" · ")}</div>
                          )}
                        </>
                      ) : (
                        <div className="text-sm text-muted">후보 없음</div>
                      )}
                    </div>
                    <div className="flex flex-col gap-2">
                      {e.candidate && (
                        <form action={decide}>
                          <input type="hidden" name="stagingId" value={item.stagingId} />
                          <input type="hidden" name="kind" value={e.kind} />
                          <input type="hidden" name="key" value={e.key} />
                          <input type="hidden" name="decision" value="AUTO_MERGE" />
                          <input type="hidden" name="canonicalId" value={e.candidate.canonicalId} />
                          <button type="submit" className="w-full rounded-md bg-accent px-3 py-1.5 text-sm text-white">
                            같은 {KIND_LABEL[e.kind]} — 병합
                          </button>
                        </form>
                      )}
                      <form action={decide}>
                        <input type="hidden" name="stagingId" value={item.stagingId} />
                        <input type="hidden" name="kind" value={e.kind} />
                        <input type="hidden" name="key" value={e.key} />
                        <input type="hidden" name="decision" value="CREATE_NEW" />
                        <button
                          type="submit"
                          className="w-full rounded-md border border-line bg-background px-3 py-1.5 text-sm hover:border-accent"
                        >
                          다른 {KIND_LABEL[e.kind]} — 새로 만들기
                        </button>
                      </form>
                    </div>
                  </li>
                ))}
              </ul>
            </li>
          ))}
        </ul>
      )}
      <p className="text-xs text-muted">
        결정은 다음 <code>publish_gold_catalog</code> 실행(asset 또는 15분 주기)에서 canonical DB에 반영됩니다.
      </p>
    </div>
  );
}
