export const GENRE_LABEL: Record<string, string> = {
  romance: "로맨스",
  comedy: "코미디",
  melodrama: "멜로",
  fantasy: "판타지",
  thriller: "스릴러",
  mystery: "미스터리",
  crime: "범죄",
  action: "액션",
  medical: "의학",
  legal: "법정",
  historical: "사극",
  family: "가족",
  youth: "청춘",
  office: "오피스",
  sf: "SF",
  horror: "공포",
  daily: "일일",
};

export const CREDIT_LABEL = {
  ACTOR: "출연",
  DIRECTOR: "연출",
  WRITER: "극본",
  PRODUCER: "제작",
} as const;

export const LINK_LABEL: Record<string, string> = {
  OFFICIAL_VOD: "공식 다시보기",
  BROADCASTER_PAGE: "방송사 페이지",
  OTT_DETAIL: "OTT",
  OFFICIAL_CLIP: "공식 클립",
  OFFICIAL_OST: "공식 OST",
};

export function genreLabel(code: string): string {
  return GENRE_LABEL[code] ?? code;
}

/** "2016.12.02" style, or "" when unknown. */
export function fmtDate(iso?: string): string {
  return iso ? iso.replaceAll("-", ".") : "";
}

/** "2016.12.02 – 2017.01.21" / "2016.12.02 –" / "". */
export function fmtRange(start?: string, end?: string): string {
  if (!start) return "";
  return end ? `${fmtDate(start)} – ${fmtDate(end)}` : `${fmtDate(start)} –`;
}

export function yearOf(iso?: string): number | undefined {
  return iso ? Number(iso.slice(0, 4)) : undefined;
}
