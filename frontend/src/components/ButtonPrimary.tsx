import React, { ButtonHTMLAttributes } from 'react';

interface ButtonPrimaryProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  children: React.ReactNode;
}

export const ButtonPrimary: React.FC<ButtonPrimaryProps> = ({ children, className = '', ...rest }) => {
  return (
    <button className={`btn-primary ${className}`} {...rest}>
      {children}
    </button>
  );
};

export default ButtonPrimary;
