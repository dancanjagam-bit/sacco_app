import React from "react";

const Button = React.forwardRef(function Button({
  as: Component = "button",
  variant = "primary",
  size = "md",
  className = "",
  type = "button",
  children,
  loading = false,
  ...props
}, ref) {
  const isDisabled = Boolean(props.disabled || loading);
  const componentProps = Component === "button" ? {
    type,
    disabled: isDisabled,
    "aria-busy": loading || undefined,
  } : { "aria-disabled": isDisabled || undefined };
  const classes = ["ui-button", "ui-button-" + variant, "ui-button-" + size, loading && "ui-button-loading", className].filter(Boolean).join(" ");
  return <Component ref={ref} className={classes} {...componentProps} {...props} disabled={Component === "button" ? isDisabled : props.disabled}>
    {loading && <span className="ui-button-spinner" aria-hidden="true" />}
    {children}
  </Component>;
});

export default Button;
