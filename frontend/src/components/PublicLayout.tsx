import {Link, NavLink} from "react-router-dom";
import type {ReactNode} from "react";
import BrandLogo from "./BrandLogo";
import "../styles/public.css";

export function PublicLayout({children}:{children:ReactNode}){
 return <div className="public-site"><header className="public-nav"><Link to="/" aria-label="HIOP home"><BrandLogo/></Link><nav aria-label="Public navigation"><NavLink to="/features">Features</NavLink><NavLink to="/pricing">Pricing</NavLink><a href="/#security">Security</a></nav><div className="public-nav-actions"><Link to="/login">Sign in</Link><Link className="public-button small" to="/get-started">Get started</Link></div></header><main>{children}</main><footer className="public-footer"><div><BrandLogo/><p>Hospitality IT operations, connected.</p></div><div><strong>Product</strong><Link to="/features">Features</Link><Link to="/pricing">Pricing</Link><a href="/#security">Security</a></div><div><strong>Company</strong><Link to="/get-started?intent=demo">Request a demo</Link><span>About · Coming soon</span><span>Contact · Coming soon</span></div><div><strong>Legal</strong><span>Privacy · Coming soon</span><span>Terms · Coming soon</span></div></footer></div>
}
