import { render } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import OrangeTree, { type TreeStage, type FruitSize } from '../components/OrangeTree'

const STAGES: TreeStage[] = ['seed', 'sprout', 'sapling', 'tree', 'grand']

const FRUIT_SELECTOR = 'circle[fill="rgb(var(--accent-rgb))"]'

describe('OrangeTree', () => {
  it.each(STAGES)('%s 단계가 렌더된다', (stage) => {
    const { container } = render(<OrangeTree stage={stage} />)
    const svg = container.querySelector(`svg[aria-label="orange-tree-${stage}"]`)
    expect(svg).not.toBeNull()
  })

  it.each(['seed', 'sprout'] as TreeStage[])(
    '%s 단계는 수관이 없어 fruitCount를 줘도 열매를 그리지 않는다',
    (stage) => {
      const { container } = render(<OrangeTree stage={stage} fruitCount={5} />)
      expect(container.querySelectorAll(FRUIT_SELECTOR)).toHaveLength(0)
    },
  )

  it('fruitCount가 7을 넘으면 7개로 clamp된다', () => {
    const { container } = render(<OrangeTree stage="tree" fruitCount={99} />)
    expect(container.querySelectorAll(FRUIT_SELECTOR)).toHaveLength(7)
  })

  it('fruitCount가 음수면 0개로 clamp된다', () => {
    const { container } = render(<OrangeTree stage="tree" fruitCount={-3} />)
    expect(container.querySelectorAll(FRUIT_SELECTOR)).toHaveLength(0)
  })

  it('fruitCount만큼만 열매가 그려진다', () => {
    const { container } = render(<OrangeTree stage="grand" fruitCount={3} />)
    expect(container.querySelectorAll(FRUIT_SELECTOR)).toHaveLength(3)
  })

  it('fruitSize 3종이 서로 다른 반지름을 만든다', () => {
    const radiusOf = (fruitSize: FruitSize) => {
      const { container } = render(
        <OrangeTree stage="tree" fruitCount={1} fruitSize={fruitSize} />,
      )
      const circle = container.querySelector(FRUIT_SELECTOR)
      return circle?.getAttribute('r')
    }

    const small = radiusOf('small')
    const medium = radiusOf('medium')
    const large = radiusOf('large')

    expect(small).not.toEqual(medium)
    expect(medium).not.toEqual(large)
    expect(small).not.toEqual(large)
  })

  it('sapling 단계는 수관이 작아 열매 반지름이 더 작다', () => {
    const { container: saplingContainer } = render(
      <OrangeTree stage="sapling" fruitCount={1} fruitSize="medium" />,
    )
    const { container: treeContainer } = render(
      <OrangeTree stage="tree" fruitCount={1} fruitSize="medium" />,
    )
    const saplingRadius = Number(
      saplingContainer.querySelector(FRUIT_SELECTOR)?.getAttribute('r'),
    )
    const treeRadius = Number(treeContainer.querySelector(FRUIT_SELECTOR)?.getAttribute('r'))

    expect(saplingRadius).toBeLessThan(treeRadius)
  })
})
