import Link from "next/link";
import { graph } from "@/lib/graph";
import { CREDIT_LABEL } from "@/lib/format";

const CREDIT: Record<string, string> = { ACTED_IN: CREDIT_LABEL.ACTOR, DIRECTED: CREDIT_LABEL.DIRECTOR, WROTE: CREDIT_LABEL.WRITER };

/** Graph neighborhood of a drama (DM-805/806). Renders nothing when the graph is unavailable. */
export async function RelatedDramas({ dramaId }: { dramaId: number }) {
  const data = await graph.related(dramaId);
  if (!data || (data.by_people.length === 0 && data.by_ost_artists.length === 0)) return null;

  return (
    <section className="space-y-4">
      {data.by_people.length > 0 && (
        <div>
          <h2 className="eyebrow mb-4">Ⅳ · 출연진·제작진이 함께한 다른 작품</h2>
          <ul className="grid gap-2 sm:grid-cols-2">
            {data.by_people.map((d) => (
              <li key={d.id}>
                <Link
                  href={`/dramas/${d.slug}`}
                  className="block rounded-lg border border-line bg-card px-4 py-3 text-sm transition hover:border-line-strong hover:bg-card-2"
                >
                  <span className="text-base font-semibold tracking-tight">{d.title}</span>
                  {d.year && <span className="ml-2 text-xs text-muted">{d.year}</span>}
                  <p className="mt-0.5 text-xs text-muted">
                    {d.via
                      .slice(0, 4)
                      .map((v) => `${v.name}${v.credit !== "ACTED_IN" ? ` (${CREDIT[v.credit] ?? v.credit})` : ""}`)
                      .join(" · ")}
                    {d.via.length > 4 ? ` 외 ${d.via.length - 4}명` : ""}
                  </p>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}
      {data.by_ost_artists.length > 0 && (
        <div>
          <h2 className="eyebrow mb-4">Ⅴ · 같은 OST 가수가 부른 다른 작품</h2>
          <ul className="flex flex-wrap gap-2 text-sm">
            {data.by_ost_artists.map((d) => (
              <li key={d.id}>
                <Link
                  href={`/dramas/${d.slug}`}
                  className="btn inline-block"
                >
                  {d.title}
                  <span className="ml-1 text-xs text-muted">({d.artists.map((a) => a.name).join(", ")})</span>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
