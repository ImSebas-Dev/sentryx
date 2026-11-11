import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import PageGuide from '../PageGuide'
import { GUIDES } from '../guides'

describe('PageGuide', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => vi.restoreAllMocks())

  it('muestra los pasos en orden la primera vez', () => {
    render(<PageGuide id="alerts" />)
    const steps = screen.getAllByRole('listitem')
    expect(steps).toHaveLength(GUIDES.alerts.steps.length)
    expect(steps[0]).toHaveTextContent(GUIDES.alerts.steps[0])
  })

  it('se oculta y lo recuerda solo para esa pantalla', async () => {
    const user = userEvent.setup()
    const { unmount } = render(<PageGuide id="alerts" />)
    const toggle = screen.getByRole('button', { name: /Cómo usar esta página/ })
    expect(toggle).toHaveAttribute('aria-expanded', 'true')

    await user.click(toggle)
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByRole('listitem')).not.toBeInTheDocument()
    unmount()

    const { unmount: unmountAgain } = render(<PageGuide id="alerts" />)
    expect(screen.queryByRole('listitem')).not.toBeInTheDocument()
    unmountAgain()

    render(<PageGuide id="reports" />)
    expect(screen.getAllByRole('listitem').length).toBeGreaterThan(0)
  })

  it('se puede volver a abrir', async () => {
    const user = userEvent.setup()
    localStorage.setItem('sentryx_guide_hidden_alerts', '1')
    render(<PageGuide id="alerts" />)
    await user.click(screen.getByRole('button', { name: /Ver pasos/ }))
    expect(screen.getAllByRole('listitem').length).toBeGreaterThan(0)
    expect(localStorage.getItem('sentryx_guide_hidden_alerts')).toBeNull()
  })

  it('funciona aunque el navegador bloquee localStorage', async () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('bloqueado') })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('bloqueado') })
    const user = userEvent.setup()
    render(<PageGuide id="alerts" />)
    await user.click(screen.getByRole('button', { name: /Cómo usar esta página/ }))
    expect(screen.queryByRole('listitem')).not.toBeInTheDocument()
  })

  it('no pinta nada con una guía que no existe', () => {
    const { container } = render(<PageGuide id="no-existe" />)
    expect(container).toBeEmptyDOMElement()
  })

  it('cada guía es corta y no repite pasos', () => {
    Object.entries(GUIDES).forEach(([id, guide]) => {
      expect(guide.steps.length, id).toBeGreaterThanOrEqual(2)
      expect(guide.steps.length, id).toBeLessThanOrEqual(7)
      expect(new Set(guide.steps).size, id).toBe(guide.steps.length)
    })
  })
})
