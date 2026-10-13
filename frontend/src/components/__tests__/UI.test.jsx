/**
 * Sentryx — Tests de componentes UI reutilizables.
 * Verifica que los badges, scores y cards renderizan correctamente.
 */
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import {
  SeverityBadge, TypeBadge, StatusBadge,
  ScoreBar, ScoreNumber, MitreBadge,
  StatCard, EmptyState, ErrorBanner,
} from '../../components/UI'
import { ShieldCheck } from 'lucide-react'

// ── SeverityBadge ─────────────────────────────────────────
describe('SeverityBadge', () => {
  it('renderiza cada nivel de severidad', () => {
    const severities = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW']
    severities.forEach(sev => {
      const { unmount } = render(<SeverityBadge severity={sev} />)
      expect(screen.getByText(sev)).toBeInTheDocument()
      unmount()
    })
  })

  it('aplica estilos de rojo para CRITICAL', () => {
    render(<SeverityBadge severity="CRITICAL" />)
    const el = screen.getByText('CRITICAL')
    expect(el.className).toMatch(/red/)
  })

  it('aplica estilos de verde para LOW', () => {
    render(<SeverityBadge severity="LOW" />)
    const el = screen.getByText('LOW')
    expect(el.className).toMatch(/green/)
  })
})

// ── TypeBadge ─────────────────────────────────────────────
describe('TypeBadge', () => {
  const cases = [
    ['bec',     'BEC'],
    ['whaling', 'Whaling'],
    ['spear',   'Spear'],
    ['clone',   'Clone'],
    ['vishing', 'Vishing'],
    ['smishing','Smishing'],
    ['generic', 'Genérico'],
    ['unknown', 'Sin clasificar'],
  ]

  it.each(cases)('renderiza etiqueta correcta para tipo "%s"', (type, label) => {
    render(<TypeBadge type={type} />)
    expect(screen.getByText(label)).toBeInTheDocument()
  })

  it('renderiza tipo desconocido sin crash', () => {
    render(<TypeBadge type="tipo_inexistente" />)
    // Para tipos no mapeados, TypeBadge usa el fallback 'unknown' label
    // Para tipos no mapeados, TypeBadge devuelve el tipo literal
    expect(screen.getByText('tipo_inexistente')).toBeInTheDocument()
  })
})

// ── StatusBadge ───────────────────────────────────────────
describe('StatusBadge', () => {
  const cases = [
    ['new',          'Nueva'],
    ['acknowledged', 'En revisión'],
    ['resolved',     'Resuelta'],
    ['false_pos',    'Falso positivo'],
  ]

  it.each(cases)('renderiza etiqueta correcta para status "%s"', (status, label) => {
    render(<StatusBadge status={status} />)
    expect(screen.getByText(label)).toBeInTheDocument()
  })
})

// ── ScoreBar ──────────────────────────────────────────────
describe('ScoreBar', () => {
  it('muestra el score redondeado', () => {
    render(<ScoreBar score={82.7} />)
    expect(screen.getByText('83')).toBeInTheDocument()
  })

  it('clampea scores mayores a 100', () => {
    render(<ScoreBar score={150} />)
    expect(screen.getByText('100')).toBeInTheDocument()
  })

  it('clampea scores menores a 0', () => {
    render(<ScoreBar score={-10} />)
    expect(screen.getByText('0')).toBeInTheDocument()
  })

  it('aplica color rojo para scores críticos (≥85)', () => {
    const { container } = render(<ScoreBar score={90} />)
    const bar = container.querySelector('.bg-red-solid')
    expect(bar).toBeInTheDocument()
  })

  it('aplica color naranja para scores altos (70–84)', () => {
    const { container } = render(<ScoreBar score={75} />)
    const bar = container.querySelector('.bg-orange-solid')
    expect(bar).toBeInTheDocument()
  })

  it('aplica color amarillo para scores sospechosos (40–69)', () => {
    const { container } = render(<ScoreBar score={55} />)
    const bar = container.querySelector('.bg-yellow-solid')
    expect(bar).toBeInTheDocument()
  })

  it('aplica color verde para scores bajos (<40)', () => {
    const { container } = render(<ScoreBar score={20} />)
    const bar = container.querySelector('.bg-green-solid')
    expect(bar).toBeInTheDocument()
  })
})

// ── ScoreNumber ───────────────────────────────────────────
describe('ScoreNumber', () => {
  it('muestra el número redondeado', () => {
    render(<ScoreNumber score={82.6} />)
    expect(screen.getByText('83')).toBeInTheDocument()
  })

  it('aplica clase roja para score crítico', () => {
    render(<ScoreNumber score={90} />)
    expect(screen.getByText('90').className).toMatch(/red/)
  })

  it('aplica clase verde para score bajo', () => {
    render(<ScoreNumber score={10} />)
    expect(screen.getByText('10').className).toMatch(/green/)
  })
})

// ── MitreBadge ────────────────────────────────────────────
describe('MitreBadge', () => {
  it('renderiza la técnica MITRE', () => {
    render(<MitreBadge technique="T1566.001" />)
    expect(screen.getByText('T1566.001')).toBeInTheDocument()
  })

  it('no renderiza nada si no hay técnica', () => {
    const { container } = render(<MitreBadge technique={null} />)
    expect(container.firstChild).toBeNull()
  })

  it('usa fuente monospace', () => {
    render(<MitreBadge technique="T1566.002" />)
    const el = screen.getByText('T1566.002')
    expect(el.className).toMatch(/mono/)
  })
})

// ── StatCard ──────────────────────────────────────────────
describe('StatCard', () => {
  it('muestra label y valor', () => {
    render(<StatCard label="Total alertas" value={42} />)
    expect(screen.getByText('Total alertas')).toBeInTheDocument()
    expect(screen.getByText('42')).toBeInTheDocument()
  })

  it('muestra subtexto cuando se proporciona', () => {
    render(<StatCard label="Críticas" value={5} sub="Acción inmediata" />)
    expect(screen.getByText('Acción inmediata')).toBeInTheDocument()
  })

  it('muestra — cuando el valor es null', () => {
    render(<StatCard label="Test" value={null} />)
    expect(screen.getByText('—')).toBeInTheDocument()
  })

  it('renderiza icono cuando se proporciona', () => {
    render(<StatCard label="Test" value={0} icon={ShieldCheck} />)
    // El icono renderiza como SVG
    expect(document.querySelector('svg')).toBeInTheDocument()
  })
})

// ── EmptyState ────────────────────────────────────────────
describe('EmptyState', () => {
  it('muestra título y descripción', () => {
    render(
      <EmptyState
        icon={ShieldCheck}
        title="Sin alertas"
        description="No hay nada aquí todavía."
      />
    )
    expect(screen.getByText('Sin alertas')).toBeInTheDocument()
    expect(screen.getByText('No hay nada aquí todavía.')).toBeInTheDocument()
  })

  it('renderiza el action cuando se proporciona', () => {
    render(
      <EmptyState
        title="Vacío"
        action={<button>Crear primero</button>}
      />
    )
    expect(screen.getByRole('button', { name: 'Crear primero' })).toBeInTheDocument()
  })
})

// ── ErrorBanner ───────────────────────────────────────────
describe('ErrorBanner', () => {
  it('muestra el mensaje de error', () => {
    render(<ErrorBanner message="El servidor no responde." />)
    expect(screen.getByText('El servidor no responde.')).toBeInTheDocument()
  })

  it('no renderiza nada si message es null', () => {
    const { container } = render(<ErrorBanner message={null} />)
    expect(container.firstChild).toBeNull()
  })

  it('llama onDismiss al hacer clic en ×', async () => {
    const onDismiss = vi.fn()
    const { getByRole } = render(
      <ErrorBanner message="Error test" onDismiss={onDismiss} />
    )
    const btn = getByRole('button')
    btn.click()
    expect(onDismiss).toHaveBeenCalledOnce()
  })
})
