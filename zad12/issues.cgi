#! /usr/bin/perl -I ../../perl5/lib/perl5
use strict;
use warnings;

#use Crypt::PBKDF2 qw(new);
use Digest::SHA qw( sha512_base64 );
use CGI qw(:standard);
use CGI::Session;
use CGI::Debug;
use HTML::Template;
use Tie::File;
use HTTP::Date;

use MyDB;

use constant CGI_PATH => 'issues.cgi';
use constant EXPIRE_TIME => '+15m';
use constant STATUSES => 'nowe', 'eskalacja', 'ponownie otwarte', 'analiza', 'wysłano mail', 
    'odrzucone', 'zrealizowane', 'eskalowane' ;
use constant TIME_PERIODS => ' < godzina', '< dzień', '< tydzień', '< 30 dni', '> 30 dni';
use constant HOUR => 60*60;
use constant DAY => 24*HOUR;
use constant WEEK => 7*DAY;

my $cgi = new CGI;
$cgi->charset('utf-8');
my $session = CGI::Session->load($cgi) or die CGI::Session->errstr;
#print $cgi->header();
#print "$session: " . $session->is_expired . "<br>" . $session->param() ."<br>";

#session unaware - report_issue and create_issue
if ( 'GET' eq $cgi->request_method  && $cgi->param && 'report_issue' eq $cgi->param('action'))  {
    show_page('templates/report_issue.html', CGI => CGI_PATH);
    exit;
} elsif ('POST' eq $cgi->request_method && 'create_issue' eq $cgi->param('action')) {
    create_issue($cgi);
    exit;
}

#session aware
if ($session->is_expired) {
    show_page('templates/msg_redirect.html',
        CGI => CGI_PATH,
        MSG => "Sesja wygasła"
    );
    $session->delete;
    exit;
} elsif (not $cgi->param) {
    show_page('templates/main_page.html');
    exit;
} elsif ('POST' eq $cgi->request_method && 'login' eq $cgi->param('action')) {
    login($cgi);
    exit;
} elsif ($cgi->param && $cgi->param('action') ) {
    my $action = $cgi->param('action');
    if (not $session->is_empty) {
        if ( 'GET' eq $cgi->request_method  ) {
            #GET method uses and action selected
            if ($action eq 'show_issue') {
                show_issue($cgi);
                exit;
            } elsif ($action eq 'edit_issue') {
                edit_issue($cgi);
                exit;
            } elsif ($action eq 'issue_list') {
                show_issue_list($cgi);
                exit;
            } elsif ($action eq 'statistics') {
                show_statistics();
                exit;
            } elsif ($action eq 'logout') {
                logout($cgi);
                exit;
            }
        } elsif ('POST' eq $cgi->request_method ) {
            #POST method used and action selected
            if ($action eq 'add_comment' ) {
                add_comment($cgi);
            } elsif ($action eq 'escale_issue' ) {
                escale_issue($cgi);
            } elsif ($action eq 'change_status') {
                change_status($cgi);    
            }
        } 
    } else {
        show_page('templates/msg_redirect.html',
            CGI => CGI_PATH,
            MSG => "Pusta sesja lub sesja wygasła"
        );
    }
} else {
    #wrong query
    die "Złe zapytanie.";
}


sub show_page {
    my ($path, @parameters) = @_;
    my $page = HTML::Template->new(filename => $path, associate => $session);
    $page->param(@parameters);
    print $cgi->header;
    print $page->output;
}

sub template {
    my ($path, @parameters) = @_;
    my $page = HTML::Template->new(filename => $path);
    $page->param(@parameters);
    return $page->output;
}

sub show_statistics {
    show_page('templates/statistics.html',
        BY_STATUS => list_by_status(),
        BY_TIME => list_by_time()
    );
}

sub list_by_time {
    my %counters = ();
    #initialize counters
    foreach my $period((TIME_PERIODS)) {
        foreach my $status(('zrealizowane', 'odrzucone', 'w toku')) {
            $counters{ $period }{ $status } = 0;
        }
    }
    #count statuses
    my @records = query_records(DB_ISSUES, 'all');
    foreach my $record(@records ) {
        my ($id, $date, $ecalates, $escalated_by, $url, $desc, $user, $email, $status ) = @$record;
        my $serve_time;
        if ($status ne 'zrealizowane' && $status ne 'odrzucone') {
            $status = 'w toku';
            $serve_time = time - $date;
        } else {
            my @transitions = query_records(DB_TRANSITIONS, 1, $id);
            my $transition = pop @transitions;
            my $end_date = $transition->[3];
            $serve_time = $end_date - $date;
        }
        my $period;
        if ($serve_time < HOUR) {
            $period = (TIME_PERIODS)[0];
        } elsif ($serve_time < DAY) {
            $period = (TIME_PERIODS)[1];
        } elsif ($serve_time < WEEK) {
            $period = (TIME_PERIODS)[2];
        } elsif ($serve_time < 30*DAY) {
            $period = (TIME_PERIODS)[3];
        } else {
            $period = (TIME_PERIODS)[4];
        }
        $counters{ $period }{ $status } += 1;
    };
    #make template list
    my @tmpl_list;
      foreach my $period((TIME_PERIODS)) {
        push(@tmpl_list, { TIME_PERIOD => $period,
            ENDED => $counters{ $period }{ 'zrealizowane' },
            INVALID => $counters{ $period }{ 'odrzucone' },
            GOING => $counters{ $period }{  'w toku'}
         });
    }
    return \@tmpl_list;
}

sub list_by_status {
    my %counters = ();
    #initialize counters
    foreach my $status((STATUSES)) {
        $counters{ $status } = 0;
    }
    #count statuses
    my @records = query_records(DB_ISSUES, 'all');
    foreach my $record(@records ) {
        my ($id, $date, $ecalates, $escalated_by, $url, $desc, $user, $email, $status ) = @$record;
        $counters{ $status } += 1;
    };
    #make template list
    my @tmpl_list;
    foreach my $key(sort keys %counters) {
        push(@tmpl_list, { STATUS => $key,
            COUNT => $counters{$key}
         });
    }
    return \@tmpl_list;  
}

sub show_issue_list {
    my ($cgi) = @_;
    show_page('templates/issue_list.html',
        LIST => list_issues()
    );
}

sub list_issues {
    my @tmpl_list;
    my @records = query_records(DB_ISSUES, 'all');
    foreach my $record(@records ) {
        my ($id, $date, $ecalates, $escalated_by, $url, $desc, $user, $email, $status ) = @$record;
        push(@tmpl_list, { ID => $id,
            DATESTAMP => time_str($date),
            STATUS => $status,
            CGI => CGI_PATH,
         });
    }
    return \@tmpl_list;
}

sub show_issue {
    my ($cgi) = @_;
    my $id = $cgi->param('id');
    my @records = query_records(DB_ISSUES, 0, $id);
    if (@records == 1) {
        my $record = $records[0];
        my ($id, $date, $escalates, $escalated_by, $url, $desc, $user, $email, $status ) = @$record;
        show_page('templates/show_issue.html', 
            ID => $id,
            ESCALATES => $escalates,
            ESCALATED => $escalated_by,
            URL => $url,
            DESC => decode_nl($desc),
            USER => $user,
            MAIL => $email,
            STATUS => $status,
            COMMENTS => list_comments($id),
            HISTORY => list_transitions($id),
            CGI => CGI_PATH . '?action=show_issue'
        );
    } else {
        show_page('templates/msg_redirect',
            CGI => CGI_PATH,
            MSG => "Błąd w trakcie pobierania zgłoszenia o #ID$id");
    }
}

sub edit_issue {
    my ($cgi) = @_;
    my $id = $cgi->param('id');
    my @records = query_records(DB_ISSUES, 0, $id);
    if (@records == 1) {
        my $record = $records[0];
        my ($id, $date, $escalates, $escalated_by, $url, $desc, $user, $email, $status ) = @$record;
        show_page('templates/edit_issue.html', 
            ID => $id,
            ESCALATES => $escalates,
            ESCALATED => $escalated_by,
            URL => $url,
            DESC => decode_nl($desc),
            USER => $user,
            MAIL => $email,
            STATUS => $status,
            INACTIVE_STATUS => ($status eq 'zrealizowane' || $status eq 'odrzucone' || $status eq 'eskalowane'),
            STATUS_LIST => list_statuses($status),
            COMMENTS => list_comments($id),
            HISTORY => list_transitions($id),
            CGI => CGI_PATH . '?action=edit_issue'
        );
    } else {
        show_page('templates/msg_redirect',
            CGI => CGI_PATH,
            MSG => "Błąd w trakcie pobierania zgłoszenia o #ID$id");
    }
}

sub list_statuses {
    my ($status) = @_;
    my @options;
    if ('nowe' eq $status || 'eskalacja' eq $status || 'ponownie otwarte' eq $status) {
        @options = ('analiza', 'wysłano mail', 'odrzucone');
    } elsif ('analiza' eq $status) {
        @options = ('wysłano mail', 'zrealizowane');
    } elsif ('wysłano mail' eq $status) {
        @options = ('analiza', 'zrealizowane')
    } elsif ('zrealizowane' eq $status || 'odrzucone' eq $status || 'eskalowane' eq $status) {
        @options = ();
    } else {
        die "Niewłaściwy status zgłoszenia";
    }
    my @tmpl_list;
    foreach my $option(@options) {
        push(@tmpl_list, { OPT => $option});
    }
    return \@tmpl_list;
}

sub list_comments {
    my ($issue_id)= @_;
    my @tmpl_list;
    my @records = query_records(DB_COMMENTS, 1, $issue_id);
    foreach my $record(@records ) {
        push(@tmpl_list, { USER => $record->[2],
                DATESTAMP => time_str($record->[3]),
                TEXT => decode_nl($record->[4]) }
        );
    }
    return \@tmpl_list;
}

sub list_transitions {
    my ($issue_id)= @_;
    my @tmpl_list;
    my @records = query_records(DB_TRANSITIONS, 1, $issue_id);
    foreach my $record(@records ) {
        push(@tmpl_list, { USER => $record->[2],
                DATESTAMP => time_str($record->[3]),
                STATUS => $record->[4]}
        );
    }
    return \@tmpl_list;
}

sub create_issue {
    my ($cgi ) = @_;
    die "Wrong POST" unless $cgi->param() == 6;
    my $url = $cgi->param('url');
    my $desc = code_nl(scalar($cgi->param('desc')));
    my $user = $cgi->param('user');
    my $email = $cgi->param('email');
    my $status = 'nowe';
    
    my $datestamp = str2time($cgi->param('datestamp'));    
    my $time = $datestamp ? $datestamp : time;
    
    #adding to db
    my $data = join(',', $time,'','',$url,$desc,$user,$email,$status);
    my $id = add_record(DB_ISSUES, $data);
    
    #show success page
    show_page('templates/msg_redirect.html', 
        CGI => CGI_PATH,
        MSG => "Utworzono zgłoszenie ID#$id ".time2str($time),
        TIME => 3
    );
}

sub escale_issue {
    my ($cgi ) = @_;
    die "Wrong POST" unless $cgi->param() == 4;
    my $escalated_id = $cgi->param('escalated_id');
    my $reason = code_nl(scalar($cgi->param('reason')));
    
    my $datestamp = str2time($cgi->param('datestamp'));    
    my $time = $datestamp ? $datestamp : time;
    
    #query for escalated issue
    my @records = query_records(DB_ISSUES, 0, $escalated_id);
    if (@records == 1) {
        my $record = $records[0];
        my ($escalated_id, $date, $ecalates, $escalated_by, $url, $old_desc, $user, $email, $status ) = @$record;
        #merge description and escalation reason
        my $desc = "$reason%nl%";
        foreach my $line(split('%nl%', $old_desc)) {
            $desc = join('%nl%', $desc, ">>$line");
        }
        #change parameters to logged user
        $user = $session->param('LOGGED_USER');
        $email = $session->param('LOGGED_EMAIL');
        $status = 'eskalacja';
        #adding to db
        my $data = join(',',$time,$escalated_id, '', $url, code_nl($desc), $user, $email, $status);
        my $id = add_record(DB_ISSUES, $data);
        #modify escalated issue
        modify_record(DB_ISSUES, 0, $escalated_id, 3, $id);
        set_status($escalated_id, 'eskalowane', $time);
        #show success page
        show_page('templates/msg_redirect.html', 
        CGI => CGI_PATH . "?action=show_issue&id=$id",
        MSG => "Utworzono zgłoszenie ID#$id eskalujące ID#$escalated_id",
        TIME => 5
        );
    } else {
        die "Query returned more than one record.";
    }
}

sub time_str {
    my ($time) = @_;
    
    return time2str($time);
}

sub add_comment {
    my ($cgi) = @_;
    die "Wrong POST" unless $cgi->param() == 4;
    my $issue_id = $cgi->param('issue_id');
    my $text = $cgi->param(code_nl(scalar('text')));
    my $user = $session->param('LOGGED_USER');
    
    my $datestamp = str2time($cgi->param('datestamp'));    
    my $time = $datestamp ? $datestamp : time;
        
    #adding to db
    my $data = join(',', $issue_id, $user, $time, $text);
    my $id = add_record(DB_COMMENTS, $data);
        show_page('templates/msg_redirect.html',
            CGI => CGI_PATH . "?action=edit_issue&id=$issue_id",
            MSG => "Dodano komentarz do zgłoszenia ID$issue_id",
            TIME => 2
        );
}

sub change_status{
    my ($cgi) = @_;
    die "Wrong POST" unless $cgi->param() == 4;
    my $issue_id = $cgi->param('issue_id');
    my $status = $cgi->param('status');
    
    my $datestamp = str2time($cgi->param('datestamp'));    
    my $time = $datestamp ? $datestamp : time;
    
    set_status($issue_id, $status, $time);
    show_page('templates/msg_redirect.html',
        CGI => CGI_PATH ."?action=edit_issue&id=$issue_id",
        MSG => "Zmieniono status zgłoszenia ID$issue_id na $status",
        TIME => 2
    );
}

sub set_status {
    my ($issue_id, $status, $time) = @_;
    my $user = $session->param('LOGGED_USER');
    
    #moifying issue status in db
    modify_record(DB_ISSUES, 0, $issue_id, 8, $status);
    #adding transition to db
    my $data = join(',', $issue_id, $user, $time, $status);    
    my $id = add_record(DB_TRANSITIONS, $data);
    #when closing check if escalates any other issue
    if($status eq 'zrealizowane' || $status eq 'odrzucone') {
        my $escalates = ((query_records(DB_ISSUES,0,$issue_id))[0])->[2];
        if ($escalates) {
            set_status($escalates, 'ponownie otwarte', $time);
        }
    }
}
sub login {
    my ($cgi) = @_;
    my $login = $cgi->param('login');
    my $password = $cgi->param('pwd');
    
    my @records = query_records(DB_ADMINS,1,$login);
    if (@records == 1)  {
        #user found in db
        my $expected_hash = ($records[0])->[2];
        my $email = ($records[0])->[3];
        chomp $expected_hash;
        #my $pbkdf2 = Crypt::PBKDF2->new();
        if ($expected_hash eq sha512_base64($password)) {
            #password valid
            my $session = CGI::Session->new($cgi)
                or die CGI::Session->errstr;
            $session->param(LOGGED => 1);
            $session->param(LOGGED_USER => $login);
            $session->param(LOGGED_EMAIL => $email);
            $session->expire(EXPIRE_TIME);
            print $session->header();
            print template('templates/msg_redirect.html',
                CGI => CGI_PATH,
                MSG => "Zalogowano"
            );
            return;
        } 
    } else {
        die "Za dużo trafień w bazie DB_ADMINS";
    }
    show_page('templates/main_page.html', MSG=>"Błędny login lub hasło");
}

sub logout {
    show_page('templates/msg_redirect.html', 
    CGi => CGI_PATH,
    MSG => "Wylogowano");
    $session->delete;
} 