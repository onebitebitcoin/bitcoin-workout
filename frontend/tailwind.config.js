/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        // 라틴·한글·숫자를 한 가족으로 묶는다. DM Sans는 한글 글리프가 없어
        // 한국어가 전부 OS 기본 서체로 떨어지고 있었다.
        body: ['IBM Plex Sans KR', 'Apple SD Gothic Neo', 'Malgun Gothic', 'sans-serif'],
        sans: ['IBM Plex Sans KR', 'Apple SD Gothic Neo', 'Malgun Gothic', 'sans-serif'],
        mono: ['IBM Plex Mono', 'SFMono-Regular', 'ui-monospace', 'monospace'],
      },
      // 타입 스케일 6단. 읽는 글자의 바닥은 13px(label)이고,
      // 11px(eyebrow)은 대문자 섹션 머리표 전용이다.
      // text-xs / text-sm / text-[10px] 등 기존 클래스는 화면 이관이 끝날 때까지 함께 산다.
      fontSize: {
        display: ['32px', { lineHeight: '34px', letterSpacing: '-0.02em', fontWeight: '700' }],
        title:   ['21px', { lineHeight: '28px', letterSpacing: '-0.01em', fontWeight: '600' }],
        lead:    ['17px', { lineHeight: '24px', letterSpacing: '-0.005em', fontWeight: '600' }],
        body:    ['15px', { lineHeight: '23px' }],
        label:   ['13px', { lineHeight: '18px', fontWeight: '500' }],
        eyebrow: ['11px', { lineHeight: '12px', letterSpacing: '0.10em', fontWeight: '600' }],
      },
      // 라운드는 두 종류. card는 모든 면, pill은 아바타·상태점·토글에만.
      borderRadius: {
        card: '14px',
        pill: '9999px',
      },
      keyframes: {
        'ping-once': {
          '0%':   { transform: 'scale(0.8)', opacity: '1' },
          '60%':  { transform: 'scale(1.2)', opacity: '0.8' },
          '100%': { transform: 'scale(1.0)', opacity: '0' },
        },
        'heart-burst': {
          '0%':   { transform: 'scale(1)' },
          '30%':  { transform: 'scale(1.5)' },
          '60%':  { transform: 'scale(0.9)' },
          '100%': { transform: 'scale(1)' },
        },
        'heart-shrink': {
          '0%':   { transform: 'scale(1)' },
          '40%':  { transform: 'scale(0.7)' },
          '100%': { transform: 'scale(1)' },
        },
        'shimmer': {
          '0%':   { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
        'confetti-fall': {
          '0%':   { transform: 'translateY(-20px) rotate(0deg)', opacity: '1' },
          '100%': { transform: 'translateY(100vh) rotate(720deg)', opacity: '0' },
        },
      },
      animation: {
        'ping-once':      'ping-once 0.5s ease-out forwards',
        'heart-burst':    'heart-burst 0.4s ease-out forwards',
        'heart-shrink':   'heart-shrink 0.3s ease-out forwards',
        'shimmer':        'shimmer 1.5s ease-in-out infinite',
        'confetti-fall':  'confetti-fall linear forwards',
      },
      colors: {
        accent: {
          DEFAULT: 'var(--accent)',
          fg: 'var(--accent-fg)',
          text: 'var(--accent-text, var(--accent))',
        },
        theme: {
          page: 'var(--bg-page)',
          surface: 'var(--bg-surface)',
          surface2: 'var(--bg-surface-2)',
          border: 'var(--border)',
          primary: 'var(--text-primary)',
          muted: 'var(--text-muted)',
          // subtle은 10px 글자를 옅어 보이게 하려고만 존재했다.
          // 화면 이관이 끝나면 지우고 muted 2단으로 간다.
          subtle: 'var(--text-subtle)',
        },
        // 상태색. 지금까지 토큰이 없어서 red-300/400/500, green-400/500이
        // 화면마다 섞여 있었다 (팔레트 직접 호출 142곳).
        danger: 'var(--danger)',
        success: 'var(--success)',
      },
    },
  },
  plugins: [],
}
