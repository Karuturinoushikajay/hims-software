import * as React from "react";

import { cn } from "@/lib/utils";

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "default" | "outline" | "ghost" | "danger";
  size?: "sm" | "md" | "lg";
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = "default", size = "md", ...props }, ref) => {
    return (
      <button
        ref={ref}
        className={cn(
          "inline-flex items-center justify-center rounded-md font-medium transition-colors disabled:opacity-50",
          size === "sm" && "h-8 px-3 text-sm",
          size === "md" && "h-10 px-4 text-sm",
          size === "lg" && "h-11 px-6",
          variant === "default" && "bg-brand-600 text-white hover:bg-brand-700",
          variant === "outline" && "border border-slate-300 bg-white hover:bg-slate-50",
          variant === "ghost" && "hover:bg-slate-100",
          variant === "danger" && "bg-red-600 text-white hover:bg-red-700",
          className,
        )}
        {...props}
      />
    );
  },
);
Button.displayName = "Button";
