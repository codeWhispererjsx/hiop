import {useState} from "react";
import {Link, NavLink} from "react-router-dom";
import BrandLogo from "./BrandLogo";
import ThemeToggle from "./ThemeToggle";
import {Icon} from "./Icon";
import "../styles/public.css";

export function PublicLayout({children}:{children:React.ReactNode}){
	const [menuOpen,setMenuOpen]=useState(false);
	const closeMenu=()=>setMenuOpen(false);
	return <div className="public-site"><header className="public-nav"><Link to="/" aria-label="HIOP home" onClick={closeMenu}><BrandLogo/></Link><button className="public-menu-toggle" type="button" aria-expanded={menuOpen} aria-controls="public-navigation" onClick={()=>setMenuOpen(value=>!value)}><Icon name={menuOpen?"close":"menu"} aria-hidden="true"/><span>{menuOpen?"Close":"Menu"}</span></button><nav id="public-navigation" className={menuOpen?"is-open":""} aria-label="Public navigation"><NavLink to="/features" onClick={closeMenu}>Features</NavLink><NavLink to="/pricing" onClick={closeMenu}>Pricing</NavLink><a href="/#security" onClick={closeMenu}>Security</a></nav><div className="public-nav-actions"><ThemeToggle className="public-theme-toggle"/><Link className="public-button small" to="/get-started" onClick={closeMenu}>Download for Windows</Link></div></header><main>{children}</main><footer className="public-footer"><div><BrandLogo/><p>Hospitality IT operations, connected.</p></div><div><strong>Product</strong><Link to="/features">Features</Link><Link to="/pricing">Pricing</Link><a href="/#security">Security</a></div><div><strong>Company</strong><Link to="/get-started?intent=demo">Request a demo</Link><span>About · Coming soon</span><span>Contact · Coming soon</span></div><div><strong>Legal</strong><span>Privacy · Coming soon</span><span>Terms · Coming soon</span></div></footer></div>
}
