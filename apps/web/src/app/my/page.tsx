import type { Metadata } from "next";
import { MyDramas } from "@/components/MyDramas";

export const metadata: Metadata = { title: "내 드라마" };

export default function MyPage() {
  return (
    <div className="space-y-6">
      <p className="eyebrow">Ⅲ · 내 드라마</p>
      <h1 className="display text-[clamp(2.5rem,7vw,5rem)]">내 연대기</h1>
      <MyDramas />
    </div>
  );
}
