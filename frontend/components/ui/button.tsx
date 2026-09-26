import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";
import { forwardRef, type ButtonHTMLAttributes } from "react";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 min-h-[44px] rounded-xl font-label-md transition-all focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary disabled:opacity-50 disabled:pointer-events-none",
  {
    variants: {
      variant: {
        primary: "bg-primary text-on-primary shadow-sm hover:bg-primary-container px-6 py-3",
        secondary:
          "bg-surface-container-lowest text-on-surface shadow-sm border border-outline-variant/50 hover:bg-surface-container px-6 py-3",
        ghost: "text-on-surface-variant hover:text-on-surface hover:bg-surface-container px-4 py-2",
        danger: "bg-error text-on-error hover:brightness-95 px-6 py-3",
      },
      size: {
        sm: "min-h-[36px] px-4 py-1.5 text-[12px]",
        md: "px-6 py-3",
        icon: "h-[44px] w-[44px] p-0",
      },
    },
    defaultVariants: { variant: "primary", size: "md" },
  }
);

export interface ButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { className, variant, size, ...props },
  ref
) {
  return <button ref={ref} className={cn(buttonVariants({ variant, size }), className)} {...props} />;
});
