import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "@/lib/utils"
import { Slot } from "radix-ui"

const buttonVariants = cva(
  "inline-flex shrink-0 items-center justify-center gap-2 rounded-lg text-sm font-semibold tracking-[-0.01em] whitespace-nowrap transition-[color,background-color,border-color,box-shadow,transform,background-position] duration-200 ease-out select-none outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 disabled:pointer-events-none disabled:opacity-50 aria-invalid:border-destructive aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground hover:bg-primary/90",
        destructive:
          "bg-destructive text-white hover:bg-destructive/90 focus-visible:ring-destructive/20 dark:bg-destructive/60 dark:focus-visible:ring-destructive/40",
        outline:
          "border bg-background shadow-xs hover:bg-accent hover:text-accent-foreground dark:border-input dark:bg-input/30 dark:hover:bg-input/50",
        secondary:
          "bg-secondary text-secondary-foreground hover:bg-secondary/80",
        ghost:
          "hover:bg-accent hover:text-accent-foreground dark:hover:bg-accent/50",
        link: "text-primary underline-offset-4 hover:underline",
        // 브랜드 CTA — index.html 의 .btn-primary / .btn-ghost / .btn-white
        brand:
          "bg-[image:var(--grad-btn)] bg-[length:170%_100%] font-bold tracking-tight text-white shadow-[0_1px_0_rgba(255,255,255,.25)_inset,0_10px_24px_-6px_rgba(42,91,215,.38)] duration-300 hover:-translate-y-px hover:bg-[position:100%_0] hover:shadow-[0_1px_0_rgba(255,255,255,.25)_inset,0_16px_32px_-8px_rgba(42,91,215,.42)]",
        soft: "bg-soft font-bold tracking-tight text-ink-2 hover:bg-line",
        white:
          "bg-white font-bold tracking-tight text-blue-deep shadow-[0_10px_28px_rgba(20,33,61,.18)] duration-300 hover:-translate-y-px hover:shadow-[0_14px_34px_rgba(20,33,61,.22)]",
      },
      size: {
        default: "h-9 px-4 py-2 has-[>svg]:px-3",
        xs: "h-6 gap-1 rounded-md px-2 text-xs has-[>svg]:px-1.5 [&_svg:not([class*='size-'])]:size-3",
        sm: "h-8 gap-1.5 rounded-md px-3 has-[>svg]:px-2.5",
        lg: "h-10 rounded-md px-6 has-[>svg]:px-4",
        xl: "h-14 rounded-2xl px-7 text-[17px] has-[>svg]:px-5 [&_svg:not([class*='size-'])]:size-5",
        md: "h-11 rounded-xl px-5 text-[15px]",
        icon: "size-9",
        "icon-xs": "size-6 rounded-md [&_svg:not([class*='size-'])]:size-3",
        "icon-sm": "size-8",
        "icon-lg": "size-10",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

function Button({
  className,
  variant = "default",
  size = "default",
  asChild = false,
  ...props
}: React.ComponentProps<"button"> &
  VariantProps<typeof buttonVariants> & {
    asChild?: boolean
  }) {
  const Comp = asChild ? Slot.Root : "button"

  return (
    <Comp
      data-slot="button"
      data-variant={variant}
      data-size={size}
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  )
}

export { Button, buttonVariants }
