import type { Metadata } from 'next';
import './globals.css';
export const metadata:Metadata={title:'Faculty Discovery — Find the minds behind your next idea',description:'Explore faculty, publications and research connections in a transparent academic discovery demo.',icons:{icon:'/favicon.svg',shortcut:'/favicon.svg'}};
export default function RootLayout({children}:{children:React.ReactNode}){return <html lang="en"><body>{children}</body></html>}
