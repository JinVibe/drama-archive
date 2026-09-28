import { redirect } from "next/navigation";
import { adminToken, isAdmin } from "@/lib/admin";
import { login } from "../actions";

export const dynamic = "force-dynamic";

export default async function AdminLoginPage({ searchParams }: PageProps<"/admin/login">) {
  if (await isAdmin()) redirect("/admin/review");
  const { error } = await searchParams;
  const disabled = !adminToken();

  return (
    <div className="max-w-sm space-y-4">
      <h1 className="text-2xl font-semibold">관리자 로그인</h1>
      {disabled ? (
        <p className="text-sm text-muted">
          <code>ADMIN_TOKEN</code>이 설정되지 않아 관리자 기능이 꺼져 있습니다.
        </p>
      ) : (
        <form action={login} className="space-y-3">
          <input
            type="password"
            name="token"
            placeholder="관리자 토큰"
            autoFocus
            className="w-full rounded-md border border-line bg-card px-3 py-2 focus:border-accent focus:outline-none"
          />
          {error && <p className="text-sm text-accent">토큰이 맞지 않습니다.</p>}
          <button type="submit" className="rounded-md bg-accent px-4 py-2 text-accent-fg">
            들어가기
          </button>
        </form>
      )}
      <p className="text-xs text-muted">임시 방식입니다. 소셜 로그인 + 권한(RBAC)이 들어오면 교체됩니다.</p>
    </div>
  );
}
