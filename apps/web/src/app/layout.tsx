import type { Metadata } from "next";
import Link from "next/link";
import { BASE_PATH } from "@/lib/api";
import "./globals.css";

export const metadata: Metadata = {
  metadataBase: new URL(process.env.SITE_URL ?? "http://localhost:3000"),
  title: { default: "DramaMemory", template: "%s · DramaMemory" },
  description: "내가 살아온 시절의 한국 드라마를 연도·배우·OST로 다시 만나는 추억 아카이브",
  openGraph: { siteName: "DramaMemory", locale: "ko_KR", type: "website" },
};

const NAV = [
  { n: "Ⅰ", href: "/", label: "연도별" },
  { n: "Ⅱ", href: "/search", label: "검색" },
  { n: "Ⅲ", href: "/my", label: "내 드라마" },
];

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="ko" className="h-full antialiased">
      <head>
        {/* Pretendard (variable, dynamic subset) — Korean-first typeface. */}
        <link
          rel="stylesheet"
          href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css"
        />
      </head>
      <body className="min-h-full flex flex-col font-sans">
        <header className="sticky top-0 z-20 border-b border-line bg-background/85 backdrop-blur">
          <nav className="mx-auto flex max-w-6xl items-center gap-8 px-5 py-4 text-sm">
            <Link href="/" className="display text-xl">
              Drama<span className="text-accent">Memory</span>
            </Link>
            <ul className="hidden items-center gap-6 sm:flex">
              {NAV.map((item) => (
                <li key={item.href}>
                  <Link href={item.href} className="group flex items-baseline gap-2 text-muted hover:text-foreground">
                    <span className="text-[11px] text-line-strong group-hover:text-accent">{item.n}</span>
                    {item.label}
                  </Link>
                </li>
              ))}
            </ul>
            <form action={`${BASE_PATH}/search/`} className="ml-auto hidden md:block">
              <input
                type="search"
                name="q"
                placeholder="기억나는 대로 검색"
                className="w-64 border-b border-line-strong bg-transparent px-1 py-1.5 text-sm placeholder:text-muted focus:border-accent focus:outline-none"
              />
            </form>
            <ul className="ml-auto flex gap-4 sm:hidden">
              {NAV.map((item) => (
                <li key={item.href}>
                  <Link href={item.href} className="text-muted hover:text-foreground">
                    {item.label}
                  </Link>
                </li>
              ))}
            </ul>
          </nav>
        </header>
        <main className="mx-auto w-full max-w-6xl flex-1 px-5 py-10 md:py-14">{children}</main>
        <footer className="border-t border-line px-5 py-8">
          <div className="mx-auto flex max-w-6xl flex-col gap-2 text-xs text-muted sm:flex-row sm:justify-between">
            <span>DramaMemory — 한국 드라마 추억 아카이브</span>
            <span>영상·음원을 호스팅하지 않습니다. 다시보기는 공식 링크로만 연결합니다. 데이터: Wikidata (CC0) 외</span>
          </div>
        </footer>
      </body>
    </html>
  );
}
