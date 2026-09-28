import Link from "next/link";
import { graph } from "@/lib/graph";

/** Co-stars by number of shared dramas (DM-804). A count of shared credits, nothing more. */
export async function Collaborators({ personId }: { personId: number }) {
  const data = await graph.collaborators(personId);
  if (!data || data.collaborators.length === 0) return null;

  return (
    <section>
      <h2 className="eyebrow mb-4">Ⅱ · 함께 출연한 배우</h2>
      <ul className="grid gap-2 sm:grid-cols-2">
        {data.collaborators.map((c) => (
          <li key={c.id}>
            <Link
              href={`/persons/${c.slug}`}
              className="flex items-baseline justify-between rounded-lg border border-line bg-card px-4 py-3 text-sm transition hover:border-line-strong hover:bg-card-2"
            >
              <span className="font-medium">{c.name}</span>
              <span className="text-xs text-muted">
                {c.works}편 · {c.dramas.slice(0, 2).map((d) => d.title).join(", ")}
                {c.dramas.length > 2 ? " 외" : ""}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
