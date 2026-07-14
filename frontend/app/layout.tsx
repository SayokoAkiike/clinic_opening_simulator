import type { Metadata } from "next";
import { Zen_Old_Mincho, Zen_Kaku_Gothic_New } from "next/font/google";
import "./globals.css";

const zenOldMincho = Zen_Old_Mincho({
  weight: ["400", "700"],
  subsets: ["latin"],
  variable: "--font-zen-old-mincho",
  display: "swap",
});

const zenKakuGothicNew = Zen_Kaku_Gothic_New({
  weight: ["400", "500", "700"],
  subsets: ["latin"],
  variable: "--font-zen-kaku-gothic-new",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Clinic Opening Simulator",
  description: "住所と条件を入れるだけ、5分で商圏と採算ラインがわかる開業診断ツール",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html
      lang="ja"
      className={`${zenOldMincho.variable} ${zenKakuGothicNew.variable}`}
    >
      <body>{children}</body>
    </html>
  );
}
