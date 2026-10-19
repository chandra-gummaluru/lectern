% ============================================================================
%  course.cls  (v2.1)
%  Document class for handouts, assignments, quizzes and exams.
%
%  Class options:
%    solutions  -- print solutions (answer key)
%    marking    -- print solutions and rubric comments (marking guide)
%  e.g. \documentclass[solutions]{course}. The Exam Builder's -key and -guide
%  files pass these options, so the student copy, answer key and marking
%  guide all compile from one source.
%
%  Changes from v2.0:
%    * solution: hidden text is now really hidden when solutions are off
%      (v2.0 still printed the answer, just without the frame).
%    * solutions / marking class options, and a marking environment.
%    * \StudentInfo: the cover's student-info rows can be redefined.
%    * \DigitBubbles, \answerspace, \answerbox, \correctchoice, \TrueFalse.
%    * \RoughWorkPage and \EndOfExam (were in each exam's .tex).
%    * Compact points table by default (was overridden in each exam).
%    * \SetScanMargin for scanned exams; \showpagenumbers switch;
%      \ExamDate and \Version metadata.
%    * Answer key / marking guide titles and hiding student info on them
%      happen here, not in each exam's .tex.
%  Changes in v2.2:
%    * subparts / \subpart[n] for (i), (ii) inside a part; \partpoints{n}.
%    * Answer components that show their answer only in the key:
%      \ansblank, \ansbox, \ansnum, \ansfrac, \anscells.
%    * \correctcheckbox for multiple-select questions; choice layouts.
%  Changes in v2.3:
%    * \showscorerowfalse leaves the blank Score row out of the points table.
%  Changes in v2.4:
%    * Student boxes are all one size (\StudentBoxSize, a sixteenth of the
%      text width by default) instead of stretching to fill the line.
%  Changes in v2.5:
%    * Two fields side by side are one box apart, so their boxes line up
%      with the rows above and below.
% ============================================================================

\NeedsTeXFormat{LaTeX2e}
\ProvidesClass{course}[2026/10/16 v2.5 course handout/assignment/exam/quiz class]

% ---- switches (defined first so the class options can set them) ------------
\newif\ifshowstudentinfo
\newif\ifshowpointstable
\newif\ifshowsolutions
\newif\ifshowmarking
\newif\ifshowaidsallowed
\newif\ifshowcoverinstructions
\newif\ifshowgoodluck
\newif\ifshowscorerow
\newif\ifshowpagenumbers
\showpagenumberstrue
\showscorerowtrue

\DeclareOption{solutions}{\showsolutionstrue}
\DeclareOption{marking}{\showsolutionstrue\showmarkingtrue}
\DeclareOption*{\PassOptionsToClass{\CurrentOption}{article}}
\ProcessOptions\relax
\LoadClass[11pt]{article}

% ---- required packages ------------------------------------------------------
\RequirePackage[margin=1in, top=1.75in, headsep=3mm, footskip=0.5in]{geometry}
\RequirePackage{fancyhdr}
\setlength{\headheight}{15pt}
\RequirePackage{lastpage}
\RequirePackage{tikz}
\usetikzlibrary{positioning}
\RequirePackage{enumitem}
\RequirePackage{titlesec}
\RequirePackage{xcolor}
\RequirePackage{amsmath, amssymb}
\RequirePackage{etoolbox}
\RequirePackage{ifthen}
\RequirePackage{environ}
\RequirePackage{comment}
\RequirePackage{totcount}
\RequirePackage{array}
\RequirePackage{booktabs}
\RequirePackage{longtable}
\RequirePackage{varwidth}
\RequirePackage{graphicx}

% ============================================================================
%  COURSE INFO -- defaults. Override in your .tex with \renewcommand{...}{...}
% ============================================================================
\newcommand{\University}{University Name}
\newcommand{\Department}{Department Name}
\newcommand{\CourseCode}{CSC000}
\newcommand{\CourseName}{Course Name}
\newcommand{\Term}{Term Year}
\newcommand{\Instructors}{Instructor Name}
\newcommand{\DocTitle}{Document Title}

% Optional metadata rows -- leave empty (the default) to hide them.
\newcommand{\ExamDate}{}
\newcommand{\Duration}{}
\newcommand{\Due}{}
\newcommand{\Weight}{}
\newcommand{\Version}{}

% Optional itemized lists for the cover page, e.g.
%   \renewcommand{\AidsAllowedList}{\item Non-programmable calculator}
\newcommand{\AidsAllowedList}{\item None}
\newcommand{\CoverInstructionsList}{%
  \item Do not begin until instructed to do so.
  \item Read each question carefully.
  \item Show your work where instructed; partial credit requires visible reasoning.
}

% Student-info rows on the cover (shown with \showstudentinfotrue).
% Redefine to change the fields, using \InfoBoxRow, \InfoBoxRowPair,
% \InfoLineRow or \DigitBubbles.
\newcommand{\StudentInfo}{%
  \InfoBoxRow{Last Name}{16}
  \InfoBoxRow{First Name}{16}
  \InfoBoxRowPair{UTORId (e.g. \texttt{gummalur})}{8}{Student \#}{10}
}

% ---- dotted-leader helper, e.g. "Duration:\cdotfill 90 minutes" -----------
% ("@" is a letter throughout a .cls file, so no \makeatletter is needed.)
\newcommand\cdotfill{%
  \leavevmode\cleaders\hb@xt@.44em{\hss.\hss}\hfill\kern\z@
}

% ---- blank space at the top of every page, for scanner codes ---------------
% Use in the preamble, e.g. \SetScanMargin{1.5cm}.
\newlength{\CT@scan}
\newcommand{\SetScanMargin}[1]{%
  \setlength{\CT@scan}{#1}%
  \geometry{top=\dimexpr1.75in+#1\relax}%
}

% ============================================================================
%  SOLUTIONS AND MARKING
%  solution: shown only with solutions on. Built on the comment package,
%  which reads the body line by line, so \begin{lstlisting} works inside and
%  nothing leaks into the student copy. Keep \begin{solution} and
%  \end{solution} on lines of their own.
%  marking: rubric comments, shown only with marking on, e.g.
%    \begin{marking}{Start at full}
%      \rubric{-1}{Missed the carry into bit 4}
%    \end{marking}
% ============================================================================
\definecolor{solutionrule}{gray}{0.7}
\newcommand{\CT@SolutionRule}{\noindent\textcolor{solutionrule}{\rule{\linewidth}{0.8pt}}\par}
\AtBeginDocument{%
  \ifshowsolutions
    \specialcomment{solution}{%
      \par\addvspace{12pt}\CT@SolutionRule\nobreak
      \addvspace{4pt}%
      \noindent\textbf{Solution.}\par\nobreak\smallskip
      \begin{quote}%
    }{%
      \end{quote}%
      \nobreak\addvspace{4pt}\CT@SolutionRule
      \addvspace{12pt}%
    }%
  \else
    \excludecomment{solution}%
  \fi
}
\newcommand{\ansnt}[1]{\ifshowsolutions #1\else\phantom{#1}\fi}

\NewEnviron{marking}[1]{%
  \ifshowmarking
    \par\addvspace{6pt}%
    {\small\noindent\textbf{Marking.} #1\par\nobreak
     \BODY\par}%
    \addvspace{6pt}%
  \fi
}
\newcommand{\rubric}[2]{\par\noindent\makebox[3.2em][r]{$#1$}\quad #2}

% Answer space: blank space in the student copy, nothing in the key.
\newcommand{\answerspace}[1]{\ifshowsolutions\else\par\vspace{#1}\fi}

% ============================================================================
%  STYLE -- black & white, simple.
% ============================================================================
\titleformat{\section}
  {\normalfont\Large\bfseries}{\thesection}{0.75em}{}[{\titlerule[0.8pt]}]
\titleformat{\subsection}
  {\normalfont\large\bfseries}{\thesubsection}{0.75em}{}
\titleformat{\subsubsection}
  {\normalfont\normalsize\bfseries\itshape}{\thesubsubsection}{0.75em}{}
\titlespacing*{\section}{0pt}{14pt}{6pt}
\titlespacing*{\subsection}{0pt}{10pt}{4pt}

% ---- Header / footer ---------------------------------------------------------
\pagestyle{fancy}
\fancyhf{}
\renewcommand{\headrulewidth}{0.6pt}
\renewcommand{\footrulewidth}{0.4pt}
\lhead{\CourseCode}
\chead{\DocTitle}
\rhead{\Term}
\lfoot{\CourseCode\ -- \Term\ifdefempty{\Version}{}{\ -- Version \Version}}
\cfoot{}
\rfoot{\ifshowpagenumbers Page \thepage\ of \pageref{LastPage}\fi}

\fancypagestyle{plain}{%
  \fancyhf{}
  \renewcommand{\headrulewidth}{0pt}
  \renewcommand{\footrulewidth}{0pt}
}

% Answer key and marking guide: say so in the title, and leave out the
% student-info boxes.
\AtBeginDocument{%
  \ifshowmarking
    \appto\DocTitle{ --- Marking Guide}\showstudentinfofalse
  \else\ifshowsolutions
    \appto\DocTitle{ --- Solutions}\showstudentinfofalse
  \fi\fi
}

% ============================================================================
%  STUDENT-INFO BOXES AND COVER PAGE
% ============================================================================

% Every student box is the same size, \StudentBoxSize: a sixteenth of the
% text width unless you set it, e.g. \setlength{\StudentBoxSize}{9mm}.
% A row with more boxes than fit on the line shrinks to fit.
\newlength{\StudentBoxSize}
\AtBeginDocument{\ifdim\StudentBoxSize=0pt \setlength{\StudentBoxSize}{\dimexpr\textwidth/16\relax}\fi}

% A row of n square boxes.
\newcommand{\CharBoxes}[1]{%
  \pgfmathsetlengthmacro{\CT@boxlen}{min(\StudentBoxSize, \linewidth/#1)}%
  \begin{tikzpicture}[baseline=-0.5ex, x=\CT@boxlen, y=\CT@boxlen]
    \foreach \i in {0,...,\numexpr#1-1\relax} {
      \draw[black, line width=0.7pt] (\i,0) rectangle ++(1,1);
    }
  \end{tikzpicture}%
}

\newcommand{\InfoBoxRow}[2]{%
  \noindent{\small\bfseries #1}\\[2pt]
  \noindent\CharBoxes{#2}\\[6pt]%
}

% Two box rows side by side, one box apart, so their boxes line up with the
% rows above and below (same box size as every other row).
\newcommand{\InfoBoxRowPair}[4]{%
  \pgfmathsetlengthmacro{\CT@pairbox}{min(\StudentBoxSize, \linewidth/(#2+#4+1))}%
  \pgfmathsetlengthmacro{\CT@pairgap}{\CT@pairbox}%
  \pgfmathsetlengthmacro{\CT@pairwa}{\CT@pairbox*#2}%
  \pgfmathsetlengthmacro{\CT@pairwb}{\CT@pairbox*#4}%
  \noindent
  \begin{minipage}[t]{\CT@pairwa}
    {\small\bfseries #1}\\[2pt]
    \CharBoxes{#2}%
  \end{minipage}%
  \hspace{\CT@pairgap}%
  \begin{minipage}[t]{\CT@pairwb}
    {\small\bfseries #3}\\[2pt]
    \CharBoxes{#4}%
  \end{minipage}\\[6pt]%
}

% A label and a line to write on, e.g. \InfoLineRow{Signature}{8cm}.
\newcommand{\InfoLineRow}[2]{%
  \noindent{\small\bfseries #1}\\[14pt]
  \noindent\rule{#2}{0.5pt}\\[8pt]%
}

% A box per digit with a column of 0-9 bubbles under it, for scanned exams.
\newcommand{\DigitBubbles}[2]{%
  \noindent{\small\bfseries #1}\\[2pt]
  \noindent\begin{tikzpicture}[x=7mm, y=-4.6mm]
    \foreach \i in {0,...,\numexpr#2-1\relax} {
      \draw[black, line width=0.7pt] (\i+0.05,-2.1) rectangle ++(0.9,1.55);
      \foreach \d in {0,...,9}
        \draw[black, line width=0.4pt] (\i+0.5,\d) circle (1.7mm) node[font=\tiny] {\d};
    }
  \end{tikzpicture}\\[6pt]%
}

% ---- points table, built from the previous run's .aux data -----------------
% Shows "(compile again)" on the first pass, before question data exists.
\newcounter{CT@i}

\newcommand{\CT@BuildRows}{%
  \def\CT@RowQ{}%
  \def\CT@RowP{}%
  \def\CT@RowS{}%
  \setcounter{CT@i}{1}%
  \whiledo{\value{CT@i}<\numexpr\CT@numquestions+1\relax}{%
    \ifnum\value{CT@i}=1
      \edef\CT@RowQ{\arabic{CT@i}}%
      \edef\CT@RowP{\csname CT@qpts@\arabic{CT@i}\endcsname}%
      \g@addto@macro{\CT@RowS}{\rule{0pt}{0.6cm}}%
    \else
      \edef\CT@RowQ{\CT@RowQ &\arabic{CT@i}}%
      \edef\CT@RowP{\CT@RowP &\csname CT@qpts@\arabic{CT@i}\endcsname}%
      \g@addto@macro{\CT@RowS}{&\rule{0pt}{0.6cm}}%
    \fi
    \stepcounter{CT@i}%
  }%
}

% The blank row for writing marks (left out with \showscorerowfalse).
\newcommand{\CT@ScoreRow}{Score: & \CT@RowS & \\ \hline}
\newcommand{\CT@PointsTable}{%
  \@ifundefined{CT@numquestions}{%
    \textit{(points table will appear after you compile again)}%
  }{%
    \CT@BuildRows
    \begingroup
    \setlength{\tabcolsep}{5pt}%
    \setlength{\arrayrulewidth}{0.7pt}%
    \small
    \begin{tabular}{|l|*{\CT@numquestions}{c|}c|}
      \hline
      Question: & \CT@RowQ & \textbf{Total} \\
      \hline
      Points: & \CT@RowP & \textbf{\total{gtpoints}} \\
      \hline
      \ifshowscorerow\CT@ScoreRow\fi
    \end{tabular}%
    \endgroup
  }%
}

\newcommand{\CT@MetaRow}[2]{%
  \ifdefempty{#2}{}{\noindent #1\cdotfill #2\par}%
}

% One-page cover: title block, metadata, student info, points table,
% instructions, "Good luck!". Optional pieces follow the \ifshow... switches
% (or \Duration etc. being non-empty). If several long blocks overflow onto a
% second page, shorten \CoverInstructionsList.
\newcommand{\MakeCoverPage}{%
  \thispagestyle{empty}
  \newgeometry{margin=1in, top=\dimexpr1.25in+\CT@scan\relax, footskip=0.5in}%
  \begin{center}

  \vspace*{0pt}
  {\large\scshape \University\par}
  {\Large \Department \par}

  \vspace{9pt}
  {\Large \CourseCode\par}
  \vspace{1pt}
  {\large \CourseName\par}
  \vspace{4pt}
  {\LARGE\bfseries \DocTitle\par}
  \vspace{2pt}
  {\large \Term\par}

  \vspace{7pt}
  \rule{0.75\textwidth}{0.5pt}\par
  \vspace{3pt}

  \begingroup
  \begin{minipage}{0.75\textwidth}
    \setlength{\parskip}{3pt}\setlength{\parindent}{0pt}
    \CT@MetaRow{Instructor(s)}{\Instructors}
    \CT@MetaRow{Date}{\ExamDate}
    \CT@MetaRow{Duration}{\Duration}
    \CT@MetaRow{Due}{\Due}
    \CT@MetaRow{Weight}{\Weight}
    \CT@MetaRow{Version}{\Version}
    \ifshowaidsallowed
      \noindent Aids Allowed\cdotfill
      \begin{varwidth}[t]{0.5\linewidth}\raggedright
        \begin{itemize}[leftmargin=0pt, itemsep=1pt, topsep=0pt, parsep=0pt, label={}]
          \AidsAllowedList
        \end{itemize}
      \end{varwidth}\par
    \fi
  \end{minipage}
  \endgroup

  \vspace{3pt}
  \rule{0.75\textwidth}{0.5pt}\par

  \end{center}

  \ifshowstudentinfo
    \vspace{7pt}
    \StudentInfo
  \fi

  \ifshowpointstable
    \vspace{7pt}
    \begin{center}
    \CT@PointsTable
    \end{center}
  \fi

  \ifshowcoverinstructions
    \vspace{7pt}
    \noindent\large \textbf{Instructions}
    \normalsize
    \begin{itemize}[leftmargin=2em, itemsep=0.5pt, topsep=1pt]
      \CoverInstructionsList
    \end{itemize}
  \fi

  \ifshowgoodluck
    \vspace{7pt}
    \begin{center}
    \textit{Good luck!}
    \end{center}
  \fi

  \newpage
  \restoregeometry
}

% A labelled rough-work page (left out of the answer key and marking guide).
\newcommand{\RoughWorkPage}{%
  \ifshowsolutions\else
    \clearpage
    \begin{center}
      {\large\bfseries This page is for rough work.}\\[3pt]
      \textit{Nothing on this page will be marked unless you clearly indicate,\\
      in the space provided for that question, that your answer continues here.}
    \end{center}
    \vfill\null
  \fi
}

% Closing line with the exam's total.
\newcommand{\EndOfExam}{%
  \par\bigskip
  \begin{center}
  \rule{0.5\textwidth}{0.4pt}\\[6pt]
  \textbf{End of Examination.} This examination is out of a total of \textbf{\total{gtpoints} marks}.
  \end{center}
}

% ============================================================================
%  POINTS ENGINE
%  \begin{questions} ... \end{questions}, \question[n], \begin{parts} ...
%  \end{parts}, \qpart[n]. Points are whole numbers (LaTeX counters).
%  Give points to \question[n] only if it has no parts; otherwise leave it
%  empty and give points to each \qpart[n].
% ============================================================================
\newcounter{question}
\newcounter{ctpart}
\newcounter{qpoints}
\newcounter{gtpoints}
\regtotcounter{gtpoints}

% Fillable box ("___ / 10") by default; the starred forms of \question and
% \qpart give a plain box ("10 points") for ungraded handouts.
\newcommand{\CT@PointsBoxFillable}[1]{%
  \fbox{\rule[-0.2\baselineskip]{0pt}{0.75\baselineskip}\hspace{0.3in} / #1}%
}
\newcommand{\CT@PointsBoxPlain}[1]{%
  \fbox{\small #1~point\ifnum#1=1\else s\fi}%
}
\newcommand{\FillPointsBox}[1]{\CT@PointsBoxFillable{#1}}
\newcommand{\PlainPointsBox}[1]{\CT@PointsBoxPlain{#1}}

\newcommand{\CT@FinalizeQuestion}{%
  \ifnum\value{question}>0
    \immediate\write\@auxout{%
      \string\expandafter\string\gdef\string\csname\space
      CT@qpts@\arabic{question}\string\endcsname\string{\arabic{qpoints}\string}%
    }%
  \fi
}

\newenvironment{questions}{%
  \setcounter{question}{0}%
  \setcounter{gtpoints}{0}%
  \begin{list}{}{\labelwidth=0pt\leftmargin=0pt\itemsep=12pt\topsep=6pt}
}{%
  \end{list}
  \CT@FinalizeQuestion
  \immediate\write\@auxout{\string\gdef\string\CT@numquestions{\arabic{question}}}%
}

\newcommand{\CT@question}[2]{%
  % #1 = points (possibly empty), #2 = fillable or plain
  \CT@FinalizeQuestion
  \stepcounter{question}%
  \setcounter{qpoints}{0}%
  \setcounter{ctpart}{0}%
  \item[]\textbf{Question \arabic{question}}%
  \def\CT@qarg{#1}%
  \ifx\CT@qarg\@empty
    % Points come from the parts: show last run's total, without adding it.
    \@ifundefined{CT@qpts@\arabic{question}}{}{%
      \ \ifthenelse{\equal{#2}{plain}}{\CT@PointsBoxPlain{\csname CT@qpts@\arabic{question}\endcsname}}{\CT@PointsBoxFillable{\csname CT@qpts@\arabic{question}\endcsname}}%
    }%
  \else
    \ \ifthenelse{\equal{#2}{plain}}{\CT@PointsBoxPlain{#1}}{\CT@PointsBoxFillable{#1}}%
    \addtocounter{qpoints}{#1}%
    \addtocounter{gtpoints}{#1}%
  \fi
  \hspace{0.4em}\ignorespaces
}
\newcommand{\CT@questionfillable}[1][]{\CT@question{#1}{fillable}}
\newcommand{\CT@questionplain}[1][]{\CT@question{#1}{plain}}
\newcommand{\question}{\@ifstar{\CT@questionplain}{\CT@questionfillable}}

\newenvironment{parts}{%
  \begin{list}{(\alph{ctpart})}{\usecounter{ctpart}\leftmargin=2.2em\itemsep=6pt\topsep=4pt}
}{%
  \end{list}
}

\newcommand{\CT@qpart}[2]{%
  \item%
  \def\CT@partarg{#1}%
  \ifx\CT@partarg\@empty
  \else
    \ifthenelse{\equal{#2}{plain}}{\CT@PointsBoxPlain{#1}}{\CT@PointsBoxFillable{#1}}%
    \addtocounter{qpoints}{#1}%
    \addtocounter{gtpoints}{#1}%
  \fi
  \ \ignorespaces
}
\newcommand{\CT@qpartfillable}[1][]{\CT@qpart{#1}{fillable}}
\newcommand{\CT@qpartplain}[1][]{\CT@qpart{#1}{plain}}
\newcommand{\qpart}{\@ifstar{\CT@qpartplain}{\CT@qpartfillable}}

% Sub-parts (i), (ii) inside a part. A part that has sub-parts takes no
% points itself; \partpoints{n} shows its total in a box without counting it.
\newcounter{ctsubpart}
\newenvironment{subparts}{%
  \begin{list}{(\roman{ctsubpart})}{\usecounter{ctsubpart}\leftmargin=2.2em\itemsep=6pt\topsep=4pt}
}{%
  \end{list}
}
\newcommand{\subpart}[1][]{%
  \item%
  \def\CT@subarg{#1}%
  \ifx\CT@subarg\@empty\else
    \CT@PointsBoxFillable{#1}%
    \addtocounter{qpoints}{#1}%
    \addtocounter{gtpoints}{#1}%
  \fi
  \ \ignorespaces
}
\newcommand{\partpoints}[1]{\CT@PointsBoxFillable{#1}\ \ignorespaces}

% ============================================================================
%  TABLES -- booktabs rules, captioned and centred.
%    \begin{cleantable}{Caption} \begin{tabular}{ll} ... \end{tabular} \end{cleantable}
% ============================================================================
\newenvironment{cleantable}[2][htbp]{%
  \begin{table}[#1]
  \centering
  \caption{#2}
  \vspace{4pt}
}{%
  \end{table}
}

% ============================================================================
%  MARKING SCHEME (for assignments)
%  \begin{markscheme} \criterion{Name}{Points}{Description} ...
%  \schemetotal{N} \end{markscheme}
% ============================================================================
\newenvironment{markscheme}{%
  \small
  \begin{longtable}{@{}p{0.24\linewidth}c p{0.60\linewidth}@{}}
    \toprule
    \textbf{Criterion} & \textbf{Points} & \textbf{Description} \\
    \midrule
    \endfirsthead
    \toprule
    \textbf{Criterion} & \textbf{Points} & \textbf{Description} \\
    \midrule
    \endhead
    \bottomrule
    \endfoot
}{%
  \end{longtable}
}
\newcommand{\criterion}[3]{%
  \textbf{#1} & #2 & #3 \\
  \addlinespace
}
\newcommand{\schemetotal}[1]{%
  \midrule
  \textbf{Total} & \textbf{#1} & \\
}

% ============================================================================
%  ADMONITIONS -- \begin{warning} ... \end{warning}, \begin{note} ... \end{note}
% ============================================================================
\newcommand{\CT@WarningIcon}{%
  \begin{tikzpicture}[baseline={([yshift=-0.55ex]current bounding box.center)}]
    \draw[black,line width=0.8pt,line join=round]
      (0,0) -- (0.18,0.31) -- (0.36,0) -- cycle;
    \node at (0.18,0.115) {\fontsize{6}{6}\selectfont\bfseries !};
  \end{tikzpicture}%
}
\newcommand{\CT@NoteIcon}{%
  \begin{tikzpicture}[baseline={([yshift=-0.55ex]current bounding box.center)}]
    \draw[black,line width=0.8pt] (0.19,0.19) circle (0.19);
    \node at (0.19,0.19) {\fontsize{6}{6}\selectfont\itshape i};
  \end{tikzpicture}%
}
\newlength{\CT@IconSep}
\setlength{\CT@IconSep}{1.2em}
\newcommand{\CT@StartAdmonition}[1]{%
  \par\medskip
  \noindent
  \parshape=2
    \CT@IconSep \dimexpr\linewidth-\CT@IconSep\relax
    0pt         \linewidth
  \llap{\makebox[\CT@IconSep][c]{#1}}%
  \ignorespaces
}
\newenvironment{warning}
  {\CT@StartAdmonition{\CT@WarningIcon}}
  {\par\medskip}
\newenvironment{note}
  {\CT@StartAdmonition{\CT@NoteIcon}}
  {\par\medskip}

% ============================================================================
%  QUIZ WIDGETS
% ============================================================================
% Checkbox (square) with label
\newcommand{\checkbox}[1][Option]{%
  \begin{tikzpicture}[baseline=0]
    \node[draw=black, minimum size=0.5cm] (s) {};
    \node[right=0cm of s, align=left]{#1};
  \end{tikzpicture}%
}

% Multiple-choice bubble; \correctchoice fills it in the answer key.
\newcommand{\CT@choice}[2]{%
  \begin{tikzpicture}[baseline=0]
    \node[circle, draw=black, fill=#1, minimum size=0.5cm] (s) {};
    \node[right=0cm of s, yshift=-0.3mm, align=left]{#2};
  \end{tikzpicture}%
}
\newcommand{\choice}[1][Option]{\CT@choice{white}{#1}}
\newcommand{\correctchoice}[1][Option]{\ifshowsolutions\CT@choice{black}{#1}\else\CT@choice{white}{#1}\fi}

% True / False bubbles: \tf (blank), or \TrueFalse{true} / \TrueFalse{false},
% which fills the answer in the key.
\newcommand{\CT@tf}[2]{%
  \\~\\
  \begin{tikzpicture}
    \node[circle, draw=black, fill=#1, minimum size=0.5cm] at (0,0) (t) {};
    \node[right=0cm of t, yshift=-1mm, align=left]{True};
    \node[circle, draw=black, fill=#2, minimum size=0.5cm] at (4,0) (f) {};
    \node[right=0cm of f, yshift=-1mm, align=left]{False};
  \end{tikzpicture}%
}
\newcommand{\tf}{\CT@tf{white}{white}}
\newcommand{\TrueFalse}[1]{%
  \ifshowsolutions
    \ifthenelse{\equal{#1}{true}}{\CT@tf{black}{white}}{\CT@tf{white}{black}}%
  \else\tf\fi
}

% Multiple select: \checkbox for each option, \correctcheckbox for the right
% ones (ticked in the answer key).
\newcommand{\correctcheckbox}[1][Option]{%
  \begin{tikzpicture}[baseline=0]
    \node[draw=black, minimum size=0.5cm] (s) {\ifshowsolutions$\checkmark$\fi};
    \node[right=0cm of s, align=left]{#1};
  \end{tikzpicture}%
}

% Choices laid out in n columns: \begin{choicecols}{3} \choice[..] & ... \end{choicecols}
\newenvironment{choicecols}[1]{%
  \par\smallskip\noindent
  \begin{tabular}{@{}*{#1}{p{\dimexpr\linewidth/#1-2\tabcolsep\relax}}@{}}%
}{%
  \end{tabular}\par
}

% ---- Answer components: blanks and boxes inside a question's text --------
% Each shows its answer only in the answer key.
%   \ansblank[3cm]{answer}       a line to write on
%   \ansbox{4cm}{1.2cm}{answer}  a box of a given size
%   \ansnum[2.5cm]{answer}       a one-line box for a number
%   \ansfrac[1.5cm]{num}{den}    a fraction: two boxes over each other
%   \anscells[7mm]{a,b,c,d}      a row of cells (one per list item; leave items empty for blank cells)
\newcommand{\CT@ans}[1]{\ifshowsolutions #1\fi}
\newcommand{\ansblank}[2][3cm]{\underline{\makebox[#1]{\CT@ans{#2}}}}
\newcommand{\ansbox}[3]{\fbox{\parbox[c][#2][c]{#1}{\centering\strut\CT@ans{#3}}}}
\newcommand{\ansnum}[2][2.5cm]{\fbox{\makebox[#1][c]{\rule[-0.35em]{0pt}{1.35em}\CT@ans{#2}}}}
\newcommand{\ansfrac}[3][1.5cm]{%
  \ensuremath{\vcenter{\hbox{\fbox{\makebox[#1][c]{\rule[-0.3em]{0pt}{1.2em}\CT@ans{#2}}}}\vspace{2pt}\hrule height 0.6pt\vspace{2pt}\hbox{\fbox{\makebox[#1][c]{\rule[-0.3em]{0pt}{1.2em}\CT@ans{#3}}}}}}%
}
\newcommand{\anscells}[2][7mm]{%
  \tikz[baseline=0.25*#1]{\foreach \x [count=\i from 0] in {#2} {\draw[line width=0.7pt] (\i*#1,0) rectangle ++(#1,#1); \ifshowsolutions\node at (\i*#1+0.5*#1,0.5*#1) {\x};\fi}}%
}

% Blank underline (for fill-in-the-blank prose)
\newcommand{\blank}[1][2cm]{\underline{\hspace{#1}}}

% Numeric answer box
\newcommand{\numbox}[1][5em]{%
  \begin{tabular}{|c|}\hline \hspace{#1} \\ \\ \\ \hline\end{tabular}%
}

% Answer box of a given size; the answer shows in it only in the key.
%   \answerbox{6cm}{1.5cm}{42}
\newcommand{\answerbox}[3]{%
  \par\smallskip\noindent
  \fbox{\parbox[c][#2][c]{#1}{\centering\strut\ifshowsolutions #3\fi}}\par
}

% A row of n adjacent equal-size boxes: \BoxArray[cellwidth]{n}
\newcommand{\BoxArray}[2][7mm]{%
  \noindent\begin{tabular}{|*{#2}{>{\rule{0pt}{#1}\centering\arraybackslash}p{#1}|}}
    \hline
     \\
    \hline
  \end{tabular}%
}

% Fractional answer boxes (numerator / denominator)
\newcommand{\fractional}[1][]{%
  #1%
  \begin{tabular}{|c|}\hline \hspace{5em} \\ \\ \\ \hline\end{tabular}%
  $\Bigg/$%
  \begin{tabular}{|c|}\hline \hspace{5em} \\ \\ \\ \hline\end{tabular}%
}

% ============================================================================
%  LISTINGS
%  \begin{lstlisting}[style=python] ... \end{lstlisting}
%  style=struct: the same code box for data-structure skeletons, without
%  keyword highlighting or line numbers.
% ============================================================================
\RequirePackage{listings}

\definecolor{python@bg}      {RGB}{252, 252, 252}
\definecolor{python@rule}    {RGB}{200, 200, 200}
\definecolor{python@lineno}  {RGB}{160, 160, 160}
\definecolor{python@keyword} {RGB}{ 12,  94, 173}
\definecolor{python@builtin} {RGB}{143,  47, 158}
\definecolor{python@string}  {RGB}{163,  21,  21}
\definecolor{python@comment} {RGB}{ 96, 139,  78}
\definecolor{python@decorator}{RGB}{143,  47, 158}

\lstdefinestyle{python}{
  language=Python,
  basicstyle=\ttfamily\small,
  commentstyle=\color{python@comment}\itshape,
  keywordstyle=\color{python@keyword}\bfseries,
  keywordstyle={[2]\color{python@builtin}},
  keywordstyle={[3]\color{python@decorator}},
  stringstyle=\color{python@string},
  numberstyle=\tiny\color{python@lineno},
  numbers=left,
  numbersep=10pt,
  tabsize=4,
  showstringspaces=false,
  breaklines=true,
  breakatwhitespace=true,
  frame=single,
  framesep=4pt,
  rulecolor=\color{python@rule},
  backgroundcolor=\color{python@bg},
  xleftmargin=2.3em,
  framexleftmargin=2.3em,
  morekeywords={[2]
    abs, all, any, ascii, bin, bool, breakpoint, bytearray, bytes,
    callable, chr, classmethod, compile, complex, delattr, dict, dir,
    divmod, enumerate, eval, exec, filter, float, format, frozenset,
    getattr, globals, hasattr, hash, help, hex, id, input, int,
    isinstance, issubclass, iter, len, list, locals, map, max,
    memoryview, min, next, object, oct, open, ord, pow, print,
    property, range, repr, reversed, round, set, setattr, slice,
    sorted, staticmethod, str, sum, super, tuple, type, vars, zip,
    None, True, False,
    Optional, Union, List, Dict, Tuple, Set, Any, Callable
  },
  morekeywords={[3]
    @property, @staticmethod, @classmethod, @abstractmethod,
    @dataclass, @overload
  },
}

\lstdefinestyle{struct}{
  language=,
  comment=[l]{\#},
  basicstyle=\ttfamily\small,
  commentstyle=\color{python@comment}\itshape,
  numbers=none,
  tabsize=4,
  showstringspaces=false,
  breaklines=true,
  breakatwhitespace=true,
  frame=single,
  framesep=4pt,
  rulecolor=\color{python@rule},
  backgroundcolor=\color{python@bg},
  xleftmargin=1.5em,
  framexleftmargin=1.5em,
}

\endinput
