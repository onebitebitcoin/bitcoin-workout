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
        // 헤드라인·숫자 전용. Space Grotesk엔 한글 글리프가 없어서 한글은
        // 폴백 체인을 타고 자동으로 IBM Plex Sans KR로 떨어진다 — 영문/숫자만
        // 지오메트릭 서체로 바뀌고 섞여 있는 한글은 깨지지 않는다.
        display: ['Space Grotesk', 'IBM Plex Sans KR', 'Apple SD Gothic Neo', 'Malgun Gothic', 'sans-serif'],
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
      // 그림자는 두 단만 쓴다. 이 앱은 배경이 어두워서(--bg-page: #0A0A0A)
      // 그림자는 두 단뿐이다. 흰 배경 기준의 tailwind 기본값은 이 어두운 배경에서
      // 거의 안 보이므로 알파를 높게 잡는다.
      // float: 페이지 위에 그대로 뜨는 큰 면 (시트·FAB).
      //   값은 BottomNav FAB에서 눈으로 맞춘 rgba(0,0,0,0.5)를 그대로 기준으로 삼았다.
      // pop:   잠깐 튀어나오는 작은 면 (드롭다운·토스트·배지). float보다 낮고 옅게.
      // 딤(--overlay, bg-black/50) 위에 뜨는 모달에는 그림자를 걸지 않는다. 딤이 이미
      // 뒤를 덮어 그림자가 보이지 않아서, 걸어도 CSS만 늘고 화면은 그대로다.
      boxShadow: {
        float: '0 8px 24px rgba(0, 0, 0, 0.5)',
        pop: '0 4px 12px rgba(0, 0, 0, 0.4)',
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
          DEFAULT: 'rgb(var(--accent-rgb) / <alpha-value>)',
          fg: 'var(--accent-fg)',
          text: 'var(--accent-text, rgb(var(--accent-rgb)))',
        },
        theme: {
          page: 'var(--bg-page)',
          surface: 'var(--bg-surface)',
          surface2: 'var(--bg-surface-2)',
          border: 'var(--border)',
          primary: 'var(--text-primary)',
          // 글자 회색은 두 단뿐이다. 위계는 크기와 굵기가 만든다.
          muted: 'var(--text-muted)',
        },
        // 상태색. 지금까지 토큰이 없어서 red-300/400/500, green-400/500이
        // 화면마다 섞여 있었다 (팔레트 직접 호출 142곳).
        danger: 'rgb(var(--danger-rgb) / <alpha-value>)',
        // leaf 와 success 는 같은 변수를 본다 (tokens.css 참고). 브랜드의 잎과
        // 완료 표시가 같은 초록이라, 이름만 둘이고 색은 하나다.
        leaf: 'rgb(var(--leaf-rgb) / <alpha-value>)',
        success: 'rgb(var(--leaf-rgb) / <alpha-value>)',
        warning: 'rgb(var(--warning-rgb) / <alpha-value>)',
        lightning: 'rgb(var(--lightning-rgb) / <alpha-value>)',
      },
    },
  },
  plugins: [],
}
