export type ShareCardData = {
  watched: number;
  years: { year: number; count: number }[];
  broadcasters: { nameKo: string; count: number }[];
  actors: { nameKo: string; count: number }[];
  titles: string[];
};

/** Satori-compatible JSX (flex only, inline styles). Shared by the share-card route. */
export function renderShareCard(d: ShareCardData) {
  const span = d.years.length ? `${d.years[d.years.length - 1].year} – ${d.years[0].year}` : "";
  return (
    <div
      style={{
        width: "100%",
        height: "100%",
        display: "flex",
        flexDirection: "column",
        justifyContent: "space-between",
        padding: 56,
        background: "linear-gradient(135deg, #fbf9f4 0%, #f6e4df 100%)",
        color: "#1c1a17",
        fontFamily: "sans-serif",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 26 }}>
        <span style={{ color: "#b5412e", fontWeight: 700 }}>DramaMemory</span>
        <span style={{ color: "#6b6560" }}>내 드라마 연대기</span>
      </div>

      <div style={{ display: "flex", alignItems: "baseline", gap: 24 }}>
        <span style={{ fontSize: 120, fontWeight: 700, lineHeight: 1 }}>{d.watched}</span>
        <span style={{ fontSize: 40 }}>편을 봤어요</span>
        {span && <span style={{ fontSize: 28, color: "#6b6560" }}>{span}</span>}
      </div>

      <div style={{ display: "flex", flexWrap: "wrap", gap: 10, fontSize: 24 }}>
        {d.titles.map((t) => (
          <span
            key={t}
            style={{ display: "flex", padding: "6px 14px", background: "#ffffff", border: "1px solid #e7e2d9", borderRadius: 8 }}
          >
            {t}
          </span>
        ))}
      </div>

      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 24, color: "#6b6560" }}>
        <span>{d.broadcasters.slice(0, 3).map((b) => `${b.nameKo} ${b.count}`).join(" · ")}</span>
        <span>{d.actors.slice(0, 3).map((a) => a.nameKo).join(" · ")}</span>
      </div>
    </div>
  );
}
