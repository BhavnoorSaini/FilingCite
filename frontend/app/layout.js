import "./globals.css";

export const metadata = {
  title: "FilingCite",
  description: "Answers about SEC filings that cite the exact page.",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
