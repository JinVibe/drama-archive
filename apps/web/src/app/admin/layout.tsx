import type { Metadata } from "next";
import Link from "next/link";
import { isAdmin } from "@/lib/admin";
import { logout } from "./actions";

export const metadata: Metadata = { title: "관리자", robots: { index: false, follow: false } };

export default async function AdminLayout({ children }: LayoutProps<"/admin">) {
  const admin = await isAdmin();
  return (
    <div className="space-y-6">
      <nav className="flex items-center gap-4 border-b border-line pb-3 text-sm">
        <span className="font-semibold">관리자</span>
        {admin && (
          <>
            <Link href="/admin/review" className="text-muted hover:text-foreground">
              리뷰 큐
            </Link>
            <Link href="/admin/problems" className="text-muted hover:text-foreground">
              문제 레코드
            </Link>
            <form action={logout} className="ml-auto">
              <button type="submit" className="text-muted hover:text-foreground">
                로그아웃
              </button>
            </form>
          </>
        )}
      </nav>
      {children}
    </div>
  );
}
