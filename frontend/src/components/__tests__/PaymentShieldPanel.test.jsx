import { describe, it, expect } from 'vitest'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { renderWithProviders } from '../../test/testUtils'
import { server, MOCK_USER } from '../../test/mswServer'
import PaymentShieldPanel from '../PaymentShieldPanel'
import { computeDv, isValidNit, maskAccount } from '../../utils/nit'
import { tokenStore } from '../../services/api'

const RISKY = {
  check_id: 'check-1', risky: true, intent_detected: true, verdict: 'lookalike_domain',
  message: 'El dominio se parece al de un proveedor.', status: 'pending_verification',
  supplier: { name: 'Proveedor Uno', nit: '890903938', dv: '8', contact_phone: '6015550100',
              bank_name: 'Bancolombia', account_last4: '8901' },
  invoice: { dian_url: 'https://catalogo-vpfe.dian.gov.co/document/searchqr?documentkey=abc' },
  checks: [
    { key: 'domain', label: 'Dominio del remitente', status: 'fail', detail: 'x.co' },
    { key: 'cufe', label: 'Formato del CUFE', status: 'pass', detail: '' },
  ],
}

describe('utils/nit', () => {
  it('calcula el DV igual que el backend', () => {
    expect(computeDv('890903938')).toBe('8')
    expect(computeDv('800197268')).toBe('4')
    expect(isValidNit('899999068', '1')).toBe(true)
    expect(isValidNit('899999068', '2')).toBe(false)
    expect(isValidNit('abc', '1')).toBe(false)
  })

  it('enmascara la cuenta y deja solo los últimos 4 dígitos', () => {
    expect(maskAccount('12345678901')).toBe('•••••••8901')
  })
})

describe('PaymentShieldPanel', () => {
  it('no pinta nada sin datos', () => {
    const { container } = renderWithProviders(<PaymentShieldPanel shield={null} />)
    expect(container.querySelector('section')).toBeNull()
  })

  it('muestra semáforo rojo, checks y teléfono de confianza', () => {
    renderWithProviders(<PaymentShieldPanel shield={RISKY} />)
    expect(screen.getByTestId('traffic-red')).toBeInTheDocument()
    expect(screen.getByText('No pagues todavía')).toBeInTheDocument()
    expect(screen.getByLabelText('Falló')).toBeInTheDocument()
    expect(screen.getByLabelText('Correcto')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /6015550100/ }))
      .toHaveAttribute('href', 'tel:6015550100')
    expect(screen.getByRole('link', { name: /catálogo de la DIAN/ }))
      .toHaveAttribute('rel', 'noopener noreferrer')
  })

  it('semáforo verde cuando coincide', () => {
    renderWithProviders(<PaymentShieldPanel shield={{ ...RISKY, risky: false }} />)
    expect(screen.getByTestId('traffic-green')).toBeInTheDocument()
  })

  it('registra la verificación telefónica', async () => {
    tokenStore.set('token')
    let body = null
    server.use(
      http.get('*/auth/me/', () => HttpResponse.json(MOCK_USER)),
      http.post('*/payment-shield/checks/check-1/verify/', async ({ request }) => {
        body = await request.json()
        return HttpResponse.json({ status: 'verified_by_call' })
      }),
    )
    const user = userEvent.setup()
    renderWithProviders(<PaymentShieldPanel shield={RISKY} />)
    await user.click(await screen.findByRole('button', { name: /Registrar verificación/ }))
    await user.type(screen.getByLabelText('Notas'), 'Confirmado con Ana')
    await user.click(screen.getByRole('button', { name: 'Guardar' }))
    expect(await screen.findByText('Verificado por llamada')).toBeInTheDocument()
    expect(body).toEqual({ result: 'verified_by_call', notes: 'Confirmado con Ana' })
    localStorage.clear()
  })
})
