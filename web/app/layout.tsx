import type { Metadata } from 'next';
import { Roboto_Slab, Work_Sans, JetBrains_Mono } from 'next/font/google';
import './globals.css';

const robotoSlab = Roboto_Slab({
  subsets: ['latin'],
  weight: ['400', '500', '600', '700', '800', '900'],
  variable: '--font-roboto-slab',
  display: 'swap',
});

const workSans = Work_Sans({
  subsets: ['latin'],
  weight: ['400', '500', '600', '700'],
  style: ['normal', 'italic'],
  variable: '--font-work-sans',
  display: 'swap',
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ['latin'],
  weight: ['400', '500', '600'],
  variable: '--font-jetbrains-mono',
  display: 'swap',
});

const SITE_DESCRIPTION =
  'How Philly feels about the Phillies, today. A daily fan-mood score from podcasts, Reddit, YouTube, and the MLB Stats API.';

const websiteSchema = {
  '@context': 'https://schema.org',
  '@type': 'WebSite',
  name: 'Phan-o-meter',
  alternateName: 'Phanometer',
  url: 'https://www.phanometer.com',
  description:
    'How Philly feels about the Phillies, today. A daily fan-mood score from podcasts, Reddit, YouTube, and the MLB Stats API.',
  potentialAction: {
    '@type': 'SearchAction',
    target: {
      '@type': 'EntryPoint',
      urlTemplate: 'https://www.phanometer.com/ask?q={search_term_string}',
    },
    'query-input': 'required name=search_term_string',
  },
  publisher: {
    '@type': 'Organization',
    name: 'Phan-o-meter',
    url: 'https://www.phanometer.com',
    logo: {
      '@type': 'ImageObject',
      url: 'https://www.phanometer.com/assets/wordmark.png',
    },
  },
};

export const metadata: Metadata = {
  metadataBase: new URL('https://www.phanometer.com'),
  title: {
    default: 'Phan-o-meter — Daily Phillies Fan Sentiment',
    template: '%s — Phan-o-meter',
  },
  description: SITE_DESCRIPTION,
  icons: {
    icon: '/assets/bell.png',
  },
  openGraph: {
    type: 'website',
    siteName: 'Phan-o-meter',
    url: 'https://www.phanometer.com',
    title: 'Phan-o-meter — Daily Phillies Fan Sentiment',
    description: SITE_DESCRIPTION,
    images: [
      {
        url: '/assets/og-default.png',
        width: 1200,
        height: 630,
        alt: 'Phan-o-meter — Daily Phillies Fan Sentiment',
      },
    ],
  },
  twitter: {
    card: 'summary_large_image',
    title: 'Phan-o-meter — Daily Phillies Fan Sentiment',
    description: SITE_DESCRIPTION,
    images: ['/assets/og-default.png'],
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="en"
      className={`${robotoSlab.variable} ${workSans.variable} ${jetbrainsMono.variable}`}
    >
      <body>
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(websiteSchema) }}
        />
        {children}
      </body>
    </html>
  );
}