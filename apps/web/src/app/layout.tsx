import type { Metadata } from "next";
import { Geist } from "next/font/google";
import Link from "next/link";
import "./globals.css";

const geist = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });

export const metadata: Metadata = {
  metadataBase: new URL(process.env.SITE_URL ?? "http://localhost:3000"),
  title: { default: "DramaMemory", template: "%s · DramaMemory" },
  description: "내가 살아온 시절의 한국 드라마를 연도·배우·OST로 다시 만나는 추억 아카이브",
  openGraph: { siteName: "DramaMemory", locale: "ko_KR", type: "website" },
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="ko" className={`${geist.variable} h-full antialiased`}>
      <body className="min-h-full flex flex-col font-sans">
        <header className="border-b border-line bg-card/80 backdrop-blur">
          <nav className="mx-auto flex max-w-5xl items-center gap-6 px-4 py-3 text-sm">
            <Link href="/" className="text-lg font-semibold tracking-tight">
              Drama<span className="text-accent">Memory</span>
            </Link>
            <Link href="/" className="text-muted hover:text-foreground">
              연도별
            </Link>
            <form action="/search" className="ml-auto hidden sm:block">
              <input
                type="search"
                name="q"
                placeholder="제목·배우·OST 검색"
                className="w-56 rounded-md border border-line bg-background px-3 py-1.5 text-sm focus:border-accent focus:outline-none"
              />
            </form>
            <Link href="/search" className="text-muted hover:text-foreground sm:hidden">
              검색
            </Link>
            <Link href="/my" className="text-muted hover:text-foreground">
              내 드라마
            </Link>
          </nav>
        </header>
        <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-8">{children}</main>
        <footer className="border-t border-line px-4 py-6 text-center text-xs text-muted">
          영상·음원을 호스팅하지 않습니다. 다시보기는 공식 링크로만 연결합니다.
        </footer>
      </body>
    </html>
  );
}
