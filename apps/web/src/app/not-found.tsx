import Link from "next/link";

export default function NotFound() {
  return (
    <div className="py-16 text-center">
      <h1 className="text-2xl font-semibold">찾을 수 없는 페이지예요</h1>
      <p className="mt-2 text-muted">작품이 아직 등록되지 않았거나 주소가 바뀌었을 수 있어요.</p>
      <Link href="/" className="mt-6 inline-block text-accent hover:underline">
        연도별로 찾아보기 →
      </Link>
    </div>
  );
}
