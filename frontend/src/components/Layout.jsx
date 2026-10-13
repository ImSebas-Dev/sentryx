/**
 * Sentryx v2 — Layout principal (patrón Fluent: barra superior + panel de navegación).
 * Desktop (≥ lg): panel lateral fijo.
 * Móvil/tablet:   botón de menú en la barra superior que abre un panel
 *                 lateral modal con fondo oscurecido.
 */
import { useState, useEffect, useRef } from 'react'
import { NavLink, useNavigate, useLocation, Link } from 'react-router-dom'
import { useAuth } from '../store/AuthContext'
import {
  ShieldCheck, Bell, FolderOpen, Globe2, FileSearch, LogOut,
  LayoutDashboard, Brain, Users, Menu, X, FileText, KeyRound,
} from 'lucide-react'
import { clsx } from 'clsx'
import ThemeMenu from './ThemeMenu'

const ROLE_LABELS = { admin: 'Administrador', analyst: 'Analista', viewer: 'Solo lectura' }

const NAV_SECTIONS = [
  {
    title: 'Monitoreo',
    items: [
      { to: '/',             label: 'Dashboard',       icon: LayoutDashboard },
      { to: '/alerts',       label: 'Alertas',         icon: Bell },
      { to: '/analyze',      label: 'Analizar correo', icon: FileSearch },
    ],
  },
  {
    title: 'Respuesta',
    items: [
      { to: '/incidents',    label: 'Incidentes',      icon: FolderOpen },
      { to: '/threat-intel', label: 'Threat Intel',    icon: Globe2 },
    ],
  },
  {
    title: 'Gestión',
    items: [
      { to: '/reports',      label: 'Informes',        icon: FileText },
      { to: '/retraining',   label: 'Reentrenamiento', icon: Brain },
    ],
  },
  {
    title: 'Cuenta',
    items: [
      { to: '/security',     label: 'Seguridad de la cuenta', icon: KeyRound },
    ],
  },
]

function NavItem({ to, label, icon: Icon, onClick }) {
  return (
    <NavLink
      to={to}
      end={to === '/'}
      onClick={onClick}
      className={({ isActive }) => clsx('nav-item', isActive && 'is-active')}
    >
      <Icon className="h-5 w-5 flex-shrink-0" strokeWidth={1.75} aria-hidden="true" />
      <span className="flex-1 truncate">{label}</span>
    </NavLink>
  )
}

function Avatar({ name, size = 'md' }) {
  const s = size === 'sm' ? 'h-7 w-7 text-caption' : 'h-9 w-9 text-body'
  return (
    <span className={clsx(
      'rounded-full bg-brand-tint text-brand-fg font-semibold uppercase',
      'flex items-center justify-center flex-shrink-0 ring-1 ring-brand-line', s
    )} aria-hidden="true">
      {name?.charAt(0) || 'U'}
    </span>
  )
}

function SidebarContent({ onNavClick }) {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  const handleLogout = () => {
    logout()
    navigate('/login')
    onNavClick?.()
  }

  const sections = user?.role === 'admin'
    ? NAV_SECTIONS.map(s => s.title === 'Gestión'
        ? { ...s, items: [...s.items, { to: '/pending-users', label: 'Usuarios pendientes', icon: Users }] }
        : s)
    : NAV_SECTIONS

  return (
    <div className="flex flex-col h-full">
      <nav className="flex-1 px-3 py-4 space-y-5 overflow-y-auto" aria-label="Navegación principal">
        {sections.map(section => (
          <div key={section.title}>
            <p className="text-overline px-3 mb-1.5">{section.title}</p>
            <div className="space-y-0.5">
              {section.items.map(item => (
                <NavItem key={item.to} {...item} onClick={onNavClick} />
              ))}
            </div>
          </div>
        ))}
      </nav>

      {/* Usuario */}
      <div className="px-3 pt-3 pb-3 border-t border-stroke flex-shrink-0">
        <div className="flex items-center gap-3 px-2 py-2">
          <Avatar name={user?.username} />
          <div className="min-w-0 flex-1">
            <p className="text-body font-semibold text-fg truncate">{user?.username}</p>
            <p className="text-caption text-fg-3">{ROLE_LABELS[user?.role] || user?.role}</p>
          </div>
        </div>
        <button
          onClick={handleLogout}
          className="nav-item w-full text-fg-2 hover:text-red-fg hover:bg-red-tint"
        >
          <LogOut className="h-5 w-5" strokeWidth={1.75} aria-hidden="true" />
          Cerrar sesión
        </button>
        <div className="flex flex-wrap gap-x-3 gap-y-1 px-3 pt-3 text-caption text-fg-4">
          <Link to="/terms" onClick={onNavClick} className="hover:text-fg-2 hover:underline">Términos</Link>
          <Link to="/privacy" onClick={onNavClick} className="hover:text-fg-2 hover:underline">Privacidad</Link>
          <Link to="/accessibility" onClick={onNavClick} className="hover:text-fg-2 hover:underline">Accesibilidad</Link>
        </div>
      </div>
    </div>
  )
}

export default function Layout({ children }) {
  const { user } = useAuth()
  const [drawerOpen, setDrawerOpen] = useState(false)
  const location   = useLocation()
  const drawerRef  = useRef(null)
  const menuBtnRef = useRef(null)

  // Cerrar el panel al cambiar de ruta
  useEffect(() => { setDrawerOpen(false) }, [location.pathname])

  // Cerrar con Escape
  useEffect(() => {
    const handleKey = e => { if (e.key === 'Escape') setDrawerOpen(false) }
    document.addEventListener('keydown', handleKey)
    return () => document.removeEventListener('keydown', handleKey)
  }, [])

  // Bloquear el scroll del body y mover el foco mientras el panel está abierto
  useEffect(() => {
    document.body.style.overflow = drawerOpen ? 'hidden' : ''
    if (drawerOpen) drawerRef.current?.focus()
    return () => { document.body.style.overflow = '' }
  }, [drawerOpen])

  const closeDrawer = () => {
    setDrawerOpen(false)
    menuBtnRef.current?.focus()
  }

  return (
    <div className="app-shell flex flex-col bg-canvas overflow-hidden">
      <a href="#main-content"
         className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-[60]
                    btn-primary">
        Saltar al contenido
      </a>

      {/* ── Barra superior ─────────────────────────────── */}
      <header className="flex items-center gap-2 h-12 px-2 sm:px-3 bg-nav border-b border-stroke
                         flex-shrink-0 pt-[env(safe-area-inset-top)] box-content">
        <button
          ref={menuBtnRef}
          onClick={() => setDrawerOpen(true)}
          className="btn-ghost btn-icon lg:hidden"
          aria-label="Abrir menú de navegación"
          aria-expanded={drawerOpen}
          aria-controls="mobile-drawer"
        >
          <Menu className="h-5 w-5" aria-hidden="true" />
        </button>

        <Link to="/" className="flex items-center gap-2.5 px-1.5 py-1 rounded-md min-w-0"
              aria-label="Sentryx, ir al dashboard">
          <span className="h-7 w-7 rounded-md bg-brand text-on-brand flex items-center justify-center
                           flex-shrink-0 shadow-2">
            <ShieldCheck className="h-4 w-4" strokeWidth={2.25} aria-hidden="true" />
          </span>
          <span className="text-subtitle2 font-semibold text-fg">Sentryx</span>
          <span className="hidden md:inline text-caption text-fg-3 pl-2.5 ml-0.5 border-l border-stroke truncate">
            v2.0 · Detección de phishing
          </span>
        </Link>

        <div className="flex-1" />

        <ThemeMenu />
        <span className="pl-1 pr-1" title={user?.username}>
          <Avatar name={user?.username} size="sm" />
        </span>
      </header>

      <div className="flex flex-1 min-h-0">
        {/* ── Panel de navegación (≥ lg) ────────────────── */}
        <aside className="hidden lg:flex w-60 flex-shrink-0 bg-nav border-r border-stroke flex-col">
          {!drawerOpen && <SidebarContent />}
        </aside>

        {/* ── Panel modal (< lg) ────────────────────────── */}
        {drawerOpen && (
          <>
            <div className="fixed inset-0 z-40 bg-black/40 lg:hidden animate-fade-in"
                 onClick={closeDrawer} aria-hidden="true" />
            <div
              id="mobile-drawer"
              ref={drawerRef}
              tabIndex={-1}
              role="dialog"
              aria-modal="true"
              aria-label="Menú de navegación"
              className="fixed inset-y-0 left-0 z-50 w-72 max-w-[85vw] bg-nav shadow-64
                         flex flex-col lg:hidden animate-drawer-in
                         pt-[env(safe-area-inset-top)] pb-[env(safe-area-inset-bottom)]"
            >
              <div className="flex items-center justify-between h-12 px-3 border-b border-stroke flex-shrink-0">
                <span className="text-subtitle2 font-semibold text-fg px-1.5">Menú</span>
                <button onClick={closeDrawer} className="btn-ghost btn-icon" aria-label="Cerrar menú">
                  <X className="h-5 w-5" aria-hidden="true" />
                </button>
              </div>
              <div className="flex-1 min-h-0">
                <SidebarContent onNavClick={() => setDrawerOpen(false)} />
              </div>
            </div>
          </>
        )}

        {/* ── Contenido ─────────────────────────────────── */}
        <main id="main-content" tabIndex={-1}
              className="flex-1 min-w-0 overflow-y-auto overscroll-contain
                         pb-[env(safe-area-inset-bottom)] focus:outline-none">
          {children}
        </main>
      </div>
    </div>
  )
}
