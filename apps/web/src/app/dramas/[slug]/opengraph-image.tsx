import { ImageResponse } from "next/og";
import { api } from "@/lib/api";
import { fmtRange, genreLabel, yearOf } from "@/lib/format";

export const alt = "DramaMemory";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

/** Social preview card: title, year/broadcaster, main cast. Rendered on demand. */
export default async function Image({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const d = await api.drama(slug);
  const cast = d.credits.filter((c) => c.creditType === "ACTOR" && c.mainCast).slice(0, 5);
  const year = yearOf(d.startDate);

  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          padding: 64,
          background: "linear-gradient(135deg, #0a0a0a 0%, #1b1b1b 100%)",
          color: "#f3efe6",
          fontFamily: "sans-serif",
        }}
      >
        <div style={{ display: "flex", fontSize: 28, color: "#e3b25a", fontWeight: 600 }}>
          DramaMemory
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div style={{ display: "flex", fontSize: 30, color: "#8a8780" }}>
            {[year ? `${year}년` : null, d.broadcaster?.nameKo].filter(Boolean).join(" · ")}
          </div>
          <div style={{ display: "flex", fontSize: 88, fontWeight: 700, lineHeight: 1.1 }}>
            {d.titleKo}
          </div>
          <div style={{ display: "flex", fontSize: 30, color: "#8a8780" }}>
            {[fmtRange(d.startDate, d.endDate), d.episodeCount ? `${d.episodeCount}부작` : null]
              .filter(Boolean)
              .join(" · ")}
          </div>
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 28 }}>
          <div style={{ display: "flex" }}>{cast.map((c) => c.nameKo).join(" · ")}</div>
          <div style={{ display: "flex", color: "#e3b25a" }}>{d.genres.map(genreLabel).join(" · ")}</div>
        </div>
      </div>
    ),
    size,
  );
}
