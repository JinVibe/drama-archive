import type { Metadata } from "next";
import { MyDramas } from "@/components/MyDramas";

export const metadata: Metadata = { title: "내 드라마" };

export default function MyPage() {
  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-semibold tracking-tight">내 드라마</h1>
      <MyDramas />
    </div>
  );
}
