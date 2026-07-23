import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import StepMedia, { type MediaItem } from './StepMedia'
import { combineVideoFilter } from '../../utils/videoFilter'

vi.mock('../../api/client', () => ({
  default: { post: vi.fn(() => new Promise(() => undefined)) },
}))
import client from '../../api/client'

function makeItem(kind: 'video' | 'image', id: string, durationSec?: number): MediaItem {
  return {
    id,
    kind,
    file: new File(['x'], `${id}.${kind === 'video' ? 'mp4' : 'png'}`, { type: kind === 'video' ? 'video/mp4' : 'image/png' }),
    previewUrl: `blob:${id}`,
    durationSec,
  }
}

function buildProps(overrides: Partial<React.ComponentProps<typeof StepMedia>> = {}) {
  return {
    fileInputRef: { current: null },
    items: [] as MediaItem[],
    onAddFiles: vi.fn(),
    onRemove: vi.fn(),
    onReorder: vi.fn(),
    estimatedSeconds: 0,
    error: '',
    onNext: vi.fn(),
    cartoonFilter: false,
    setCartoonFilter: vi.fn(),
    heatFilter: false,
    setHeatFilter: vi.fn(),
    ...overrides,
  }
}

describe('StepMedia', () => {
  it('아이템이 없으면 다음 버튼이 비활성', () => {
    render(<StepMedia {...buildProps()} />)
    expect(screen.getByRole('button', { name: '다음' })).toBeDisabled()
  })

  it('아이템을 렌더한다', () => {
    const items = [makeItem('image', 'a'), makeItem('video', 'b', 5)]
    render(<StepMedia {...buildProps({ items, estimatedSeconds: 8 })} />)
    expect(screen.getAllByLabelText('remove')).toHaveLength(2)
  })

  it('예상 길이가 60초를 초과하면 다음 버튼 비활성', () => {
    const items = [makeItem('video', 'b', 65)]
    render(<StepMedia {...buildProps({ items, estimatedSeconds: 65 })} />)
    expect(screen.getByRole('button', { name: '다음' })).toBeDisabled()
  })

  it('정상 구성이면 다음 클릭 시 onNext 호출', async () => {
    const onNext = vi.fn()
    const items = [makeItem('image', 'a')]
    render(<StepMedia {...buildProps({ items, estimatedSeconds: 3, onNext })} />)
    await userEvent.click(screen.getByRole('button', { name: '다음' }))
    expect(onNext).toHaveBeenCalledOnce()
  })

  it('삭제 버튼 클릭 시 onRemove(id) 호출', async () => {
    const onRemove = vi.fn()
    const items = [makeItem('image', 'a')]
    render(<StepMedia {...buildProps({ items, estimatedSeconds: 3, onRemove })} />)
    await userEvent.click(screen.getByLabelText('remove'))
    expect(onRemove).toHaveBeenCalledWith('a')
  })

  it('아이템이 없으면 필터 토글이 보이지 않는다', () => {
    render(<StepMedia {...buildProps()} />)
    expect(screen.queryAllByRole('switch')).toHaveLength(0)
  })

  it('아이템이 있으면 카툰·운동열 토글이 각각 하나씩 보인다', () => {
    const items = [makeItem('image', 'a')]
    render(<StepMedia {...buildProps({ items, estimatedSeconds: 3 })} />)
    expect(screen.getAllByRole('switch')).toHaveLength(2)
  })

  it('카툰 토글 클릭 시 setCartoonFilter(true) 호출', async () => {
    const setCartoonFilter = vi.fn()
    const items = [makeItem('image', 'a')]
    render(<StepMedia {...buildProps({ items, estimatedSeconds: 3, setCartoonFilter })} />)
    await userEvent.click(screen.getByRole('switch', { name: '카툰 필터' }))
    expect(setCartoonFilter).toHaveBeenCalledWith(true)
  })

  it('운동열 토글 클릭 시 setHeatFilter(true) 호출', async () => {
    const setHeatFilter = vi.fn()
    const items = [makeItem('image', 'a')]
    render(<StepMedia {...buildProps({ items, estimatedSeconds: 3, setHeatFilter })} />)
    await userEvent.click(screen.getByRole('switch', { name: '운동열 강조' }))
    expect(setHeatFilter).toHaveBeenCalledWith(true)
  })

  it('카툰 필터 ON이면 이미지 아이템으로 filter-preview 요청을 보낸다', async () => {
    const items = [makeItem('image', 'a')]
    render(<StepMedia {...buildProps({ items, estimatedSeconds: 3, cartoonFilter: true })} />)
    await waitFor(() =>
      expect(vi.mocked(client.post)).toHaveBeenCalledWith(
        '/videos/filter-preview',
        expect.any(FormData),
        expect.objectContaining({ responseType: 'blob' }),
      ),
    )
  })

  it('운동열 필터 ON이면 filter-preview 요청을 보낸다', async () => {
    const items = [makeItem('image', 'a')]
    render(<StepMedia {...buildProps({ items, estimatedSeconds: 3, heatFilter: true })} />)
    await waitFor(() =>
      expect(vi.mocked(client.post)).toHaveBeenCalledWith(
        '/videos/filter-preview',
        expect.any(FormData),
        expect.objectContaining({ responseType: 'blob' }),
      ),
    )
  })
})

describe('combineVideoFilter', () => {
  it('둘 다 꺼지면 undefined', () => {
    expect(combineVideoFilter(false, false)).toBeUndefined()
  })

  it('카툰만 켜지면 cartoon', () => {
    expect(combineVideoFilter(true, false)).toBe('cartoon')
  })

  it('운동열만 켜지면 heat', () => {
    expect(combineVideoFilter(false, true)).toBe('heat')
  })

  it('둘 다 켜지면 cartoon_heat', () => {
    expect(combineVideoFilter(true, true)).toBe('cartoon_heat')
  })
})
