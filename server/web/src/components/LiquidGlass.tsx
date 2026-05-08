import * as React from 'react';
import { Box, Stack, type BoxProps, type SxProps, type Theme } from '@mui/material';
import './liquidGlass.css';

export type LiquidGlassVariant = 'clear' | 'frosted' | 'layered' | 'solid';
export type LiquidGlassTone = 'neutral' | 'primary' | 'secondary' | 'success' | 'warning' | 'error' | 'muted';
export type LiquidGlassDensity = 'compact' | 'comfortable' | 'spacious';
export type LiquidGlassOrientation = 'horizontal' | 'vertical';
export type LiquidGlassStatus = 'idle' | 'active' | 'selected' | 'success' | 'warning' | 'error';
export type LiquidGlassDockPosition = 'top' | 'right' | 'bottom' | 'left' | 'floating';

export interface LiquidGlassProps extends Omit<BoxProps, 'children'> {
  children?: React.ReactNode;
  variant?: LiquidGlassVariant;
  tone?: LiquidGlassTone;
  density?: LiquidGlassDensity;
  slot?: 'topbar' | 'controls' | 'prompt' | 'candidate' | 'footer' | 'chat';
  status?: LiquidGlassStatus;
  dockPosition?: LiquidGlassDockPosition;
  active?: boolean;
  selected?: boolean;
  interactive?: boolean;
  lift?: boolean;
  disabled?: boolean;
  className?: string;
  sx?: SxProps<Theme>;
}

export interface GlassDockProps extends LiquidGlassProps {
  orientation?: LiquidGlassOrientation;
  edge?: LiquidGlassDockPosition;
}

export interface GlassToolbarProps extends LiquidGlassProps {
  orientation?: LiquidGlassOrientation;
  wrap?: boolean;
}

export interface GlassStatusRimProps extends LiquidGlassProps {
  status?: LiquidGlassStatus;
  pulse?: boolean;
  inset?: boolean;
}

function cx(...values: Array<string | false | null | undefined>) {
  return values.filter(Boolean).join(' ');
}

function glassClassName(base: string, props: LiquidGlassProps, extra?: string) {
  const {
    variant = 'frosted',
    tone = 'neutral',
    density = 'comfortable',
    status,
    dockPosition,
    active,
    selected,
    interactive,
    lift,
    disabled,
    className,
  } = props;

  return cx(
    'lg',
    base,
    `lg--${variant}`,
    `lg--${tone}`,
    `lg--${density}`,
    status && `lg-status--${status}`,
    dockPosition && `lg-dock-position--${dockPosition}`,
    active && 'is-active',
    selected && 'is-selected',
    status && status !== 'idle' && status !== 'active' && status !== 'selected' && `is-${status}`,
    interactive && 'is-interactive',
    lift && 'has-lift',
    disabled && 'is-disabled',
    extra,
    className,
  );
}

function glassStateProps(props: LiquidGlassProps) {
  const { active, selected, interactive, disabled, status, dockPosition, slot, role, tabIndex } = props;

  return {
    'data-active': active ? 'true' : undefined,
    'data-selected': selected ? 'true' : undefined,
    'data-status': status,
    'data-dock-position': dockPosition,
    'data-slot': slot,
    'aria-selected': role === 'button' ? undefined : selected || active || undefined,
    'aria-disabled': disabled || undefined,
    tabIndex: interactive && !disabled && tabIndex === undefined ? 0 : tabIndex,
  };
}

export const GlassSurface = React.forwardRef<HTMLDivElement, LiquidGlassProps>(function GlassSurface(
  {
    children,
    variant = 'frosted',
    tone = 'neutral',
    density = 'comfortable',
    status,
    dockPosition,
    slot,
    active,
    selected,
    interactive,
    lift,
    disabled,
    className,
    ...boxProps
  },
  ref,
) {
  const effectiveActive = active ?? status === 'active';
  const effectiveSelected = selected ?? status === 'selected';
  const stateProps = glassStateProps({
    active: effectiveActive,
    selected: effectiveSelected,
    interactive,
    disabled,
    status,
    dockPosition,
    slot,
    role: boxProps.role,
    tabIndex: boxProps.tabIndex,
  });

  return (
    <Box
      ref={ref}
      {...boxProps}
      {...stateProps}
      className={glassClassName('lg-surface', {
        variant,
        tone,
        density,
        status,
        dockPosition,
        active: effectiveActive,
        selected: effectiveSelected,
        interactive,
        lift,
        disabled,
        className,
      })}
    >
      {children}
    </Box>
  );
});

export const GlassPanel = React.forwardRef<HTMLDivElement, LiquidGlassProps>(function GlassPanel(props, ref) {
  return <GlassSurface ref={ref} {...props} className={cx('lg-panel', props.className)} />;
});

export const GlassCard = React.forwardRef<HTMLDivElement, LiquidGlassProps>(function GlassCard(
  { interactive = true, ...props },
  ref,
) {
  return <GlassSurface ref={ref} interactive={interactive} {...props} className={cx('lg-card', props.className)} />;
});

export const GlassDock = React.forwardRef<HTMLDivElement, GlassDockProps>(function GlassDock(
  { orientation = 'horizontal', edge, dockPosition, ...props },
  ref,
) {
  const effectiveDockPosition = dockPosition ?? edge ?? 'floating';

  return (
    <GlassSurface
      ref={ref}
      {...props}
      dockPosition={effectiveDockPosition}
      className={cx(
        'lg-dock',
        `lg-dock--${orientation}`,
        `lg-dock--${effectiveDockPosition}`,
        props.className,
      )}
    />
  );
});

export const GlassToolbar = React.forwardRef<HTMLDivElement, GlassToolbarProps>(function GlassToolbar(
  { orientation = 'horizontal', wrap = true, children, className, ...props },
  ref,
) {
  return (
    <GlassSurface
      ref={ref}
      {...props}
      className={cx('lg-toolbar', `lg-toolbar--${orientation}`, wrap && 'lg-toolbar--wrap', className)}
    >
      <Stack
        direction={orientation === 'horizontal' ? 'row' : 'column'}
        alignItems={orientation === 'horizontal' ? 'center' : 'stretch'}
        className="lg-toolbar__inner"
      >
        {children}
      </Stack>
    </GlassSurface>
  );
});

export const GlassStatusRim = React.forwardRef<HTMLDivElement, GlassStatusRimProps>(function GlassStatusRim(
  { status = 'idle', pulse = false, inset = false, children, className, ...props },
  ref,
) {
  return (
    <GlassSurface
      ref={ref}
      {...props}
      status={status}
      active={props.active ?? status === 'active'}
      selected={props.selected ?? status === 'selected'}
      tone={props.tone ?? (status === 'idle' || status === 'active' || status === 'selected' ? 'neutral' : status)}
      className={cx(
        'lg-status-rim',
        `lg-status-rim--${status}`,
        pulse && 'lg-status-rim--pulse',
        inset && 'lg-status-rim--inset',
        className,
      )}
    >
      {children}
    </GlassSurface>
  );
});

export const LiquidGlass = GlassSurface;
