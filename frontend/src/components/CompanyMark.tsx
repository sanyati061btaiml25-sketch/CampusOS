import React from 'react';

interface Props {
  company: string;
  size?: number;
}

/**
 * Clean minimal bespoke SVG brand marks inside a porcelain squircle frame
 * (replaces generic 2-letter placeholder boxes).
 */
export const CompanyMark: React.FC<Props> = ({ company, size = 48 }) => {
  const key = company.toLowerCase();

  const renderGlyph = () => {
    if (key.includes('razorpay')) {
      return (
        <svg viewBox="0 0 24 24" width="22" height="22" fill="none">
          <path d="M14.5 3L7 14.2h5.2L9.5 21L17 9.8h-5.2L14.5 3Z" fill="#072654" />
          <path d="M15.8 7.5L13 11.8h3.5l-2.3 5.2" stroke="#2563EB" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      );
    }
    if (key.includes('sarvam')) {
      return (
        <svg viewBox="0 0 24 24" width="22" height="22" fill="none">
          <circle cx="12" cy="12" r="8" stroke="#1E1B4B" strokeWidth="1.8" />
          <path d="M7.5 13c1.5-3 3.2-3 4.5 0s3 3 4.5 0" stroke="#4F46E5" strokeWidth="1.8" strokeLinecap="round" />
        </svg>
      );
    }
    if (key.includes('postman')) {
      return (
        <svg viewBox="0 0 24 24" width="22" height="22" fill="none">
          <circle cx="12" cy="12" r="8.5" stroke="#EA580C" strokeWidth="1.8" />
          <circle cx="12" cy="12" r="3" fill="#EA580C" />
          <path d="M12 3.5v3M19 15l-2.6-1.5" stroke="#EA580C" strokeWidth="1.7" strokeLinecap="round" />
        </svg>
      );
    }
    if (key.includes('swiggy')) {
      return (
        <svg viewBox="0 0 24 24" width="22" height="22" fill="none">
          <path
            d="M12 3.2c-3.9 0-7 3-7 6.8 0 4.8 7 10.8 7 10.8s7-6 7-10.8c0-3.8-3.1-6.8-7-6.8Z"
            stroke="#EA580C"
            strokeWidth="1.8"
          />
          <path d="M9.5 10.2h5M12 7.8v4.8" stroke="#EA580C" strokeWidth="1.7" strokeLinecap="round" />
        </svg>
      );
    }
    if (key.includes('microsoft')) {
      return (
        <svg viewBox="0 0 24 24" width="20" height="20" fill="none">
          <rect x="3.5" y="3.5" width="7.5" height="7.5" rx="1.2" fill="#F25022" />
          <rect x="13" y="3.5" width="7.5" height="7.5" rx="1.2" fill="#7FBA00" />
          <rect x="3.5" y="13" width="7.5" height="7.5" rx="1.2" fill="#00A4EF" />
          <rect x="13" y="13" width="7.5" height="7.5" rx="1.2" fill="#FFB900" />
        </svg>
      );
    }
    if (key.includes('atlassian')) {
      return (
        <svg viewBox="0 0 24 24" width="22" height="22" fill="none">
          <path d="M8.5 12.2L4.2 19.5h6.1l1.8-4.5c-.9-1.5-2-2.2-3.6-2.8Z" fill="#2684FF" />
          <path d="M12.6 4.5c-1.8 3.2-1.9 7-.3 10.5l2.2 4.5h5.3L12.6 4.5Z" fill="#0052CC" />
        </svg>
      );
    }
    if (key.includes('zoho')) {
      return (
        <svg viewBox="0 0 24 24" width="22" height="22" fill="none">
          <rect x="3.5" y="6.5" width="7" height="7" rx="1.6" stroke="#DC2626" strokeWidth="1.8" />
          <rect x="9" y="10.5" width="7" height="7" rx="1.6" stroke="#16A34A" strokeWidth="1.8" />
          <rect x="13.5" y="6" width="7" height="7" rx="1.6" stroke="#2563EB" strokeWidth="1.8" />
        </svg>
      );
    }
    if (key.includes('flipkart')) {
      return (
        <svg viewBox="0 0 24 24" width="22" height="22" fill="none">
          <path d="M6 8h12l-1.2 11H7.2L6 8Z" stroke="#2563EB" strokeWidth="1.8" strokeLinejoin="round" />
          <path d="M9.5 8V6.5a2.5 2.5 0 0 1 5 0V8" stroke="#F59E0B" strokeWidth="1.8" />
          <path d="M10.2 12.5h4M10.2 12.5v4" stroke="#2563EB" strokeWidth="1.7" strokeLinecap="round" />
        </svg>
      );
    }
    if (key.includes('phonepe')) {
      return (
        <svg viewBox="0 0 24 24" width="22" height="22" fill="none">
          <circle cx="12" cy="12" r="8.5" fill="#5F259F" />
          <path d="M10 8.5v7M10 9h3a2 2 0 1 1 0 4h-3" stroke="#ffffff" strokeWidth="1.8" strokeLinecap="round" />
        </svg>
      );
    }
    if (key.includes('zepto')) {
      return (
        <svg viewBox="0 0 24 24" width="22" height="22" fill="none">
          <rect x="4" y="4" width="16" height="16" rx="4.5" fill="#4C1D95" />
          <path d="M8.5 9h7l-6.5 6h7" stroke="#F472B6" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      );
    }
    if (key.includes('fractal')) {
      return (
        <svg viewBox="0 0 24 24" width="22" height="22" fill="none">
          <polygon points="12,3.5 20,17.5 4,17.5" stroke="#0F172A" strokeWidth="1.8" strokeLinejoin="round" />
          <polygon points="12,9 16,16 8,16" stroke="#0284C7" strokeWidth="1.5" strokeLinejoin="round" />
        </svg>
      );
    }
    if (key.includes('niyo')) {
      return (
        <svg viewBox="0 0 24 24" width="22" height="22" fill="none">
          <circle cx="12" cy="12" r="8.5" stroke="#0F766E" strokeWidth="1.8" />
          <path d="M9 15l2-5.5L16.5 8l-2 5.5L9 15Z" stroke="#0F766E" strokeWidth="1.6" strokeLinejoin="round" />
        </svg>
      );
    }
    if (key.includes('cred')) {
      return (
        <svg viewBox="0 0 24 24" width="22" height="22" fill="none">
          <path d="M12 3.5L19 6.5v5.5c0 4.5-3 7.5-7 8.8-4-1.3-7-4.3-7-8.8V6.5l7-3Z" stroke="#0F172A" strokeWidth="1.8" />
          <path d="M9.5 12h5" stroke="#0F172A" strokeWidth="1.8" strokeLinecap="round" />
        </svg>
      );
    }
    if (key.includes('cloudfleet')) {
      return (
        <svg viewBox="0 0 24 24" width="22" height="22" fill="none">
          <path d="M7.5 17h9a3.5 3.5 0 0 0 .4-7A5 5 0 0 0 7.2 8.8 3.8 3.8 0 0 0 7.5 17Z" stroke="#475569" strokeWidth="1.8" strokeLinejoin="round" />
        </svg>
      );
    }
    return (
      <svg viewBox="0 0 24 24" width="22" height="22" fill="none">
        <rect x="4.5" y="4.5" width="15" height="15" rx="4" stroke="#3730A3" strokeWidth="1.8" />
        <circle cx="12" cy="12" r="3" fill="#3730A3" />
      </svg>
    );
  };

  return (
    <div
      className="company-mark"
      style={{ width: size, height: size }}
      aria-hidden="true"
    >
      {renderGlyph()}
    </div>
  );
};
