import "./globals.css";

export const metadata = {
  title: "FilingCite",
  description: "Answers about SEC filings, with a citation for every number.",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
