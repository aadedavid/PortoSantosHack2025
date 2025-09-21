import React, { useState } from 'react';

export const Tooltip = ({ children, content, side = 'top' }) => {
  const [isVisible, setIsVisible] = useState(false);

  const sideClasses = {
    top: 'bottom-full left-1/2 transform -translate-x-1/2 mb-2',
    bottom: 'top-full left-1/2 transform -translate-x-1/2 mt-2',
    left: 'right-full top-1/2 transform -translate-y-1/2 mr-2',
    right: 'left-full top-1/2 transform -translate-y-1/2 ml-2'
  };

  return (
    <div className="relative inline-block">
      <div
        onMouseEnter={() => setIsVisible(true)}
        onMouseLeave={() => setIsVisible(false)}
      >
        {children}
      </div>
      {isVisible && (
        <div className={`absolute z-50 px-3 py-2 text-sm text-white bg-gray-900 rounded-lg shadow-lg whitespace-nowrap ${sideClasses[side]}`}>
          {content}
          <div className="absolute w-2 h-2 bg-gray-900 transform rotate-45" 
               style={{
                 top: side === 'bottom' ? '-4px' : side === 'top' ? 'auto' : '50%',
                 bottom: side === 'top' ? '-4px' : 'auto',
                 left: side === 'right' ? '-4px' : side === 'left' ? 'auto' : '50%',
                 right: side === 'left' ? '-4px' : 'auto',
                 marginLeft: (side === 'top' || side === 'bottom') ? '-4px' : '0',
                 marginTop: (side === 'left' || side === 'right') ? '-4px' : '0'
               }}
          />
        </div>
      )}
    </div>
  );
};

export const InfoIcon = ({ tooltip, className = "" }) => {
  return (
    <Tooltip content={tooltip}>
      <svg 
        className={`w-4 h-4 text-gray-400 hover:text-gray-600 cursor-help ${className}`}
        fill="currentColor" 
        viewBox="0 0 20 20"
      >
        <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clipRule="evenodd" />
      </svg>
    </Tooltip>
  );
};