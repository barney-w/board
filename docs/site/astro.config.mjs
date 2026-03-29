import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';

export default defineConfig({
  site: 'https://barney-w.github.io',
  base: '/board',
  integrations: [
    starlight({
      title: 'Board',
      favicon: '/favicon.svg',
      logo: {
        light: '../../docs/assets/board-logo-dark.svg',
        dark: '../../docs/assets/board-logo.svg',
      },
      social: [
        { icon: 'github', label: 'GitHub', href: 'https://github.com/barney-w/board' },
      ],
      customCss: ['./src/styles/landing.css'],
      sidebar: [
        {
          label: 'Getting Started',
          items: [
            { label: 'Quickstart', slug: 'getting-started/quickstart' },
            { label: 'For Shapers', slug: 'getting-started/for-shapers' },
            { label: 'For Developers', slug: 'getting-started/for-developers' },
          ],
        },
        {
          label: 'Reference',
          items: [
            { label: 'Manifest Schema', slug: 'reference/manifest-schema' },
            { label: 'Architecture', slug: 'reference/architecture' },
          ],
        },
      ],
    }),
  ],
});
